"""
Run a LoRA fine-tune on Together AI from finetune/out/train.jsonl.

    pip install together
    # .env: TOGETHER_API_KEY=...
    python -m finetune.together_finetune start                 # upload + create job (Qwen/Qwen3.5-4B)
    python -m finetune.together_finetune status                # poll the last job
    python -m finetune.together_finetune deploy                # dedicated endpoint (billed per minute!)
    python -m finetune.together_finetune undeploy              # delete the endpoint when eval is done

Swap the base model with --model Qwen/Qwen3.8-27B (same data, same flow).
Every `start` creates a new billed job; job ids are appended to finetune/jobs.json.
Together no longer offers serverless LoRA inference, so evaluation needs `deploy`, and
the endpoint costs money until `undeploy`.

After deploy, point the eval pipeline at it:
    QWEN_BASE_URL=https://api.together.xyz/v1  QWEN_API_KEY=$TOGETHER_API_KEY
    QWEN_TUNED_MODEL=<endpoint model name printed by deploy>
    python -m qc_eval.pipeline --models qwen_tuned --skip-judge
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from qc_eval.config import load_env

HERE = Path(__file__).resolve().parent
JOBS = HERE / "jobs.json"
DEFAULT_MODEL = "Qwen/Qwen3.5-4B"


def client():
    load_env()
    from together import Together  # imported lazily so tests and other modules do not need it
    if not os.environ.get("TOGETHER_API_KEY"):
        raise SystemExit("TOGETHER_API_KEY is not set (.env)")
    return Together()


def load_jobs():
    return json.loads(JOBS.read_text()) if JOBS.exists() else []


def save_jobs(jobs):
    JOBS.write_text(json.dumps(jobs, indent=1))


def update_job(job):
    update_job(job)


def upload(c, path):
    f = c.files.upload(file=str(path), purpose="fine-tune", check=True)
    while True:
        meta = c.files.retrieve(f.id)
        status = getattr(meta, "processing_status", "COMPLETED")
        if status == "COMPLETED":
            return f.id
        if status in ("INVALID_FORMAT", "FAILED"):
            raise SystemExit("file {} rejected: {} {}".format(path, status, getattr(meta, "validation_report", "")))
        time.sleep(5)


def cmd_start(args):
    c = client()
    train_id = upload(c, args.train)
    val_id = upload(c, args.val) if args.val and Path(args.val).exists() and Path(args.val).stat().st_size else None
    kwargs = dict(training_file=train_id, model=args.model, lora=True, n_epochs=args.epochs,
                  learning_rate=args.lr, n_checkpoints=1, warmup_ratio=0.05,
                  train_on_inputs="auto", suffix=args.suffix)
    if val_id:
        kwargs.update(validation_file=val_id, n_evals=args.epochs)
    job = c.fine_tuning.create(**kwargs)
    jobs = load_jobs()
    jobs.append({"job_id": job.id, "model": args.model, "train_file": train_id, "val_file": val_id,
                 "epochs": args.epochs, "lr": args.lr, "suffix": args.suffix,
                 "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    save_jobs(jobs)
    print("job", job.id)


def last_job(args):
    jobs = load_jobs()
    if args.job:
        return next(j for j in jobs if j["job_id"] == args.job)
    if not jobs:
        raise SystemExit("no jobs in finetune/jobs.json")
    return jobs[-1]


def cmd_status(args):
    c, job = client(), last_job(args)
    st = c.fine_tuning.retrieve(id=job["job_id"])
    job["status"] = st.status
    for key in ("api_model_object_id", "api_model_object_name", "output_name"):
        if getattr(st, key, None):
            job[key] = getattr(st, key)
    update_job(job)
    print(json.dumps(job, indent=1))


def cmd_deploy(args):
    c, job = client(), last_job(args)
    name = job.get("api_model_object_name") or job.get("output_name")
    if not name:
        raise SystemExit("job not finished or model name unknown; run status first")
    ep = c.endpoints.create(model=name, hardware=args.hardware, display_name=args.endpoint,
                            min_replicas=1, max_replicas=1, inactive_timeout=args.idle_minutes)
    job["endpoint_id"], job["endpoint_name"] = ep.id, getattr(ep, "name", None)
    update_job(job)
    print("endpoint", ep.id, "model name for QWEN_TUNED_MODEL:", job["endpoint_name"] or name)


def cmd_undeploy(args):
    c, job = client(), last_job(args)
    if not job.get("endpoint_id"):
        raise SystemExit("no endpoint recorded for this job")
    c.endpoints.delete(endpoint_id=job["endpoint_id"])
    job["endpoint_deleted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    update_job(job)
    print("deleted", job["endpoint_id"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--train", default=str(HERE / "out" / "train.jsonl"))
    s.add_argument("--val", default=str(HERE / "out" / "val.jsonl"))
    s.add_argument("--model", default=DEFAULT_MODEL)
    s.add_argument("--epochs", type=int, default=3)
    s.add_argument("--lr", type=float, default=1e-4, help="LoRA learning rate (Together default is 1e-5)")
    s.add_argument("--suffix", default="qc-lean-v1")
    for name in ("status", "deploy", "undeploy"):
        p = sub.add_parser(name)
        p.add_argument("--job", help="job id (default: last in jobs.json)")
        if name == "deploy":
            p.add_argument("--endpoint", default="qwen-qc-tuned")
            p.add_argument("--hardware", default=None, help="see `tg endpoints hardware`")
            p.add_argument("--idle-minutes", type=int, default=30, help="auto-stop after this many idle minutes")
    args = ap.parse_args(argv)
    {"start": cmd_start, "status": cmd_status, "deploy": cmd_deploy, "undeploy": cmd_undeploy}[args.cmd](args)


if __name__ == "__main__":
    main()
