import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
const modules=process.env.ARTIFACT_NODE_MODULES||path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require=createRequire(path.join(modules,'..','package.json'));
const {FileBlob,SpreadsheetFile}=await import(require.resolve('@oai/artifact-tool'));
const here=path.dirname(new URL(import.meta.url).pathname);
let src=here;
while(true) {
  try { await fs.access(path.join(src,'qc_eval/pipeline.py')); break; } catch {}
  const parent=path.dirname(src);
  if(parent===src) throw new Error('Cannot locate src/qc_eval');
  src=parent;
}
const previews='/private/tmp/together_eval_excel_runtime/previews100';
await fs.mkdir(previews,{recursive:true});
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(src,'QC_Eval_Prompt_Error_Sheet.xlsx')));
if(process.argv.includes('--inspect-only')) {
  console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1800})).ndjson);
  const image=await wb.render({sheetName:'Results',range:'E1:Q6',scale:1,format:'png'});
  await fs.writeFile(path.join(previews,'template.png'),new Uint8Array(await image.arrayBuffer()));
  process.exit(0);
}
const data=JSON.parse(await fs.readFile(path.join(here,'workbook_data.json'),'utf8'));
if(data.rows.length!==100) throw new Error('Expected 100 evaluated prompt rows');
const result=wb.worksheets.getItem('Results');
const summary=wb.worksheets.getItem('Summary');
const legend=wb.worksheets.getItem('Legend');
const feedback=wb.worksheets.getItem('QC Feedback');
const details=wb.worksheets.getItem('Judge Details');
result.getRange('F3:N102').clear({applyTo:'contents'});
result.getRange('O3:Q102').clear({applyTo:'contents'});
result.getRange('P2').values=[['Human fidelity, Qwen tuned (1-5)']];
for(const row of data.rows) {
  const index=data.prompts.findIndex(p=>p.id===row.prompt_id)+3;
  if(index<3) throw new Error('Unknown prompt ID');
  result.getRange(`L${index}:N${index}`).values=[[row.compile_errors,row.runtime_errors,row.fidelity]];
  const error=String(row.error||'').replace(/\s+/g,' ').slice(0,180);
  const note=`QC: ${row.qc_status}. Claude: ${row.judge_status}; fidelity=${row.fidelity??'unavailable'}. ${error?'QC excerpt: '+error+'... ':''}Full judge reason and QC IDs: QC Feedback. Requirement evidence: Judge Details. Original model output; no repairs.`;
  result.getRange(`Q${index}`).values=[[note]];
  const lines=Math.max(Math.ceil(data.prompts[index-3].prompt.length/75),Math.ceil(note.length/78));
  result.getRange(`A${index}:Q${index}`).format.rowHeight=Math.max(100,lines*13+14);
}
result.getRange('E3:E102').format.columnWidth=68;
result.getRange('E3:E102').format.wrapText=true;
result.getRange('Q3:Q102').format.columnWidth=70;
result.getRange('Q3:Q102').format.wrapText=true;
legend.getRange('B3').values=[['Record execution errors and prompt-adherence scores for the deployed Together 9B model across all 100 held-out prompts. The agreed comparison layout is retained; base-model and Fable columns are blank for this experiment.']];
legend.getRange('B8').values=[['All 100 test prompts are evaluated with the deployed Together 9B model. Results uses the Qwen tuned columns. The 870 training prompts are excluded. Three exact 9B smoke-test outputs and judgments are reused.']];
legend.getRange('B11').values=[['Claude judges prompt adherence with the 1-5 rubric and eight evidence dimensions. Execution failure is reported separately and does not automatically set the fidelity score to 1.']];
legend.getRange('B18').values=[['Human check columns are blank until a person reviews these exact 9B outputs. The Review column in QC Feedback records the judge flag, not a completed human review.']];
legend.getRange('B22').values=[['100 original Together 9B generations, including three reused smoke-test outputs; temperature 0; maximum 4096 output tokens; system prompt v1. No automatic repairs or mock outputs. Candidate code and QC evidence are source-hash bound.']];
legend.getRange('A24:B29').values=[
  ['Model',data.manifest.model_id],
  ['Selection','All 100 held-out prompts: 10 strategy templates with 10 prompt variants each. No training prompts are included.'],
  ['Execution','QC candidate backtests are new. Gold evidence is reused only for an identical reference source hash; its older engine version is retained in the evidence.'],
  ['Missing metrics','Failed backtests have no complete trading sequence. Missing diagnostics remain blank. Intervals require distinct fill times; DTW requires matching equity date ranges and at least 95% common daily observations.'],
  ['Provenance','Original provider outputs and QC/judge inputs remain unchanged. English report text is separate from original model output, which may contain language-instruction violations.'],
  ['Sources','runs/together_9b_eval100_20261114: manifest.json, generations/qwen_tuned/, scoring/together_9b_tuned/, and scoring/evaluations/.']
];
legend.getRange('B3:B29').format.wrapText=true;
legend.getRange('B3:B29').format.columnWidth=110;
legend.getRange('A3:B29').format.rowHeight=42;
legend.getRange('A24:A29').format.font={name:'Arial',size:10,bold:true};
legend.getRange('A24:B29').format.font.name='Arial';
for(const sheet of [feedback,details]) {
  sheet.getUsedRange().conditionalFormats.clear();
  sheet.getUsedRange().clear({applyTo:'all'});
}
function header(sheet,range,values) {
  sheet.getRange(range).values=[values];
  sheet.getRange(range).format={fill:'#1F3A5F',font:{name:'Arial',size:10,color:'#FFFFFF',bold:true},rowHeight:38,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};
}
const qcEnd=3+data.qc_rows.length;
const behaviorTitle=qcEnd+4, behaviorHeader=behaviorTitle+2;
const behaviorStart=behaviorHeader+1, behaviorEnd=behaviorHeader+data.behavior_rows.length;
const reasonTitle=behaviorEnd+4, reasonHeader=reasonTitle+2;
const reasonStart=reasonHeader+1, reasonEnd=reasonHeader+data.reason_rows.length;
feedback.getRange('A1').values=[['Together 9B: full 100-prompt evaluation, original outputs']];
feedback.getRange('A1').format.font={name:'Arial',size:14,bold:true};
header(feedback,'A3:H3',['Prompt ID','Model endpoint','Repair rounds','Compile errors','Runtime errors','Fidelity (1-5)','QC status','Review required']);
feedback.getRange(`A4:H${qcEnd}`).values=data.qc_rows;
feedback.getRange(`A4:H${qcEnd}`).format.rowHeight=42;
feedback.getRange(`A4:H${qcEnd}`).format.wrapText=true;
feedback.getRange(`C4:H${qcEnd}`).format.horizontalAlignment='center';
feedback.getRange(`A${behaviorTitle}`).values=[['Behavior diagnostics against Gold']];
header(feedback,`A${behaviorHeader}:K${behaviorHeader}`,['Prompt ID','Candidate filled orders','Gold filled orders','Candidate closed trades','Gold closed trades','Fill F1','Interval MAE (seconds)','Equity DTW','Position agreement','Behavior status','Comparison limits']);
feedback.getRange(`A${behaviorStart}:K${behaviorEnd}`).values=data.behavior_rows;
feedback.getRange(`A${behaviorStart}:K${behaviorEnd}`).format.rowHeight=52;
feedback.getRange(`A${behaviorStart}:K${behaviorEnd}`).format.wrapText=true;
feedback.getRange(`F${behaviorStart}:F${behaviorEnd}`).setNumberFormat('0.000');
feedback.getRange(`G${behaviorStart}:G${behaviorEnd}`).setNumberFormat('#,##0.0');
feedback.getRange(`H${behaviorStart}:H${behaviorEnd}`).setNumberFormat('0.000000');
feedback.getRange(`I${behaviorStart}:I${behaviorEnd}`).setNumberFormat('0.0%');
feedback.getRange(`A${reasonTitle}`).values=[['Judge reasons and QC provenance']];
header(feedback,`A${reasonHeader}:E${reasonHeader}`,['Prompt ID','Judge reason','Review notes','QC project ID','QC backtest ID']);
feedback.getRange(`A${reasonStart}:E${reasonEnd}`).values=data.reason_rows;
for(const [i,row] of data.reason_rows.entries()) {
  feedback.getRange(`A${reasonStart+i}:E${reasonStart+i}`).format.rowHeight=Math.max(100,Math.ceil(String(row[1]).length/95)*13+18);
}
feedback.getRange(`A${reasonStart}:E${reasonEnd}`).format.wrapText=true;
feedback.getRange(`A${reasonStart}:E${reasonEnd}`).format.verticalAlignment='top';
feedback.getRange(`A1:K${reasonEnd}`).format.font.name='Arial';
for(const [index,width] of [48,100,42,26,44,18,20,20,18,20,64].entries()) feedback.getRangeByIndexes(0,index,reasonEnd,1).format.columnWidth=width;
feedback.getRange(`G4:G${qcEnd}`).conditionalFormats.addCustom('G4="runtime_error"',{fill:'#FCE4D6',font:{color:'#9C0006'}});
feedback.freezePanes.freezeRows(3);
details.getRange('A1').values=[['Claude prompt-adherence evidence']];
details.getRange('A1').format.font={name:'Arial',size:14,bold:true};
header(details,'A3:F3',['Prompt ID','Dimension','Requested requirement','Judge status','Candidate line evidence','Source JSON']);
const end=3+data.dimension_rows.length;
details.getRange(`A4:F${end}`).values=data.dimension_rows;
details.getRange(`A4:F${end}`).format={font:{name:'Arial',size:10},wrapText:true,verticalAlignment:'top'};
const widths=[48,25,64,21,112,70];
for(const [c,width] of widths.entries()) details.getRangeByIndexes(0,c,end,1).format.columnWidth=width;
for(const [i,row] of data.dimension_rows.entries()) {
  const lines=Math.max(...row.map((v,c)=>Math.ceil(String(v).length/(widths[c]*1.1))));
  details.getRange(`A${i+4}:F${i+4}`).format.rowHeight=Math.max(36,lines*14+12);
}
details.freezePanes.freezeRows(3);
summary.getRange('A46:C54').clear({applyTo:'all'});
header(summary,'A46:C46',['Together 9B full test','Value','Scope']);
summary.getRange('A47:A53').values=[['Candidates evaluated'],['Completed backtests'],['Candidates with fidelity'],['Average fidelity (1-5)'],['Judge review required'],['Behavior available'],['Behavior partial']];
summary.getRange('B47:B53').formulas=[
 [`=COUNTA('QC Feedback'!A4:A${qcEnd})`],
 [`=COUNTIFS('QC Feedback'!G4:G${qcEnd},"completed")`],
 ['=D4'],
 ['=D10'],
 [`=COUNTIFS('QC Feedback'!H4:H${qcEnd},"Y")`],
 [`=COUNTIFS('QC Feedback'!J${behaviorStart}:J${behaviorEnd},"available")`],
 [`=COUNTIFS('QC Feedback'!J${behaviorStart}:J${behaviorEnd},"partial")`]];
summary.getRange('C47:C53').values=[['All 100 held-out prompts'],['Execution only'],['Includes explicit no-code grades if present'],['Original outputs, no repairs'],['Flags are not human scores'],['All behavior evidence available'],['Some metrics unavailable; see limits']];
summary.getRange('A46:C53').format.font.name='Arial';
summary.getRange('A47:C53').format.rowHeight=34;
summary.getRange('C47:C53').format.wrapText=true;
summary.getRange('A54:C54').values=[['QC results pending',null,'Service errors or deferred submissions']];
summary.getRange('B54').formulas=[[`=COUNTIFS('QC Feedback'!G4:G${qcEnd},"deferred")+COUNTIFS('QC Feedback'!G4:G${qcEnd},"infrastructure_error")+COUNTIFS('QC Feedback'!G4:G${qcEnd},"timeout")+COUNTIFS('QC Feedback'!G4:G${qcEnd},"running")`]];
summary.getRange('A54:C54').format={font:{name:'Arial',size:10},rowHeight:34,wrapText:true};
summary.getRange('B50').setNumberFormat('0.00');
summary.getRange('D4').formulas=[['=COUNT(Results!N3:N102)']];
summary.getRange('D8').formulas=[['=IF(OR(D4=0,B54>0),"-",(D5+D6)/D4)']];
summary.getRange('D9').formulas=[['=IF(OR(COUNT(Results!L3:L102)=0,B54>0),"-",COUNTIFS(Results!L3:L102,0,Results!M3:M102,0,Results!M3:M102,"<>")/COUNTA(Results!A3:A102))']];
summary.getRange('A12').values=[['Judge check (judge vs human, Qwen tuned)']];
summary.getRange('B13:B15').formulas=[
 ['=SUMPRODUCT((Results!O3:O102="Y")*ISNUMBER(Results!P3:P102)*ISNUMBER(Results!N3:N102))'],
 ['=IFERROR(SUMPRODUCT((Results!O3:O102="Y")*ISNUMBER(Results!P3:P102)*ISNUMBER(Results!N3:N102)*((Results!N3:N102-Results!P3:P102)^2)^0.5)/B13,"-")'],
 ['=IFERROR(SUMPRODUCT((Results!O3:O102="Y")*ISNUMBER(Results!P3:P102)*ISNUMBER(Results!N3:N102)*(Results!N3:N102=Results!P3:P102))/B13,"-")']];
for(let r=4;r<=10;r++) summary.getRange(`E${r}`).formulas=[[`=IF(OR($C$4=0,$D$4=0),"-",IFERROR(D${r}-C${r},"-"))`]];
wb.recalculate();
const original=result.getRange('N3').values[0][0];
const oldMean=summary.getRange('D10').values[0][0];
result.getRange('N3').values=[[original===1?5:1]];
wb.recalculate();
const newMean=summary.getRange('D10').values[0][0];
if(newMean===oldMean) throw new Error('Main summary did not update after input change');
if(summary.getRange('B50').values[0][0]!==newMean) throw new Error('Full-test summary did not update after input change');
result.getRange('N3').values=[[original]];
wb.recalculate();
if(summary.getRange('D10').values[0][0]!==oldMean) throw new Error('Original score was not restored');
result.getRange('O3:P3').values=[['Y',1]];
wb.recalculate();
if(summary.getRange('B13').values[0][0]!==1 || summary.getRange('B14').values[0][0]!==Math.abs(original-1)) throw new Error('Human comparison values: '+JSON.stringify(summary.getRange('B13:B15').values));
result.getRange('P3').values=[[original]];
wb.recalculate();
if(summary.getRange('B15').values[0][0]!==1) throw new Error('Human agreement did not recalculate');
result.getRange('O3:P3').clear({applyTo:'contents'});
wb.recalculate();
if(summary.getRange('B13').values[0][0]!==0) throw new Error('Temporary human scores were not cleared');
console.log((await wb.inspect({kind:'table',range:'Summary!A46:C54',include:'values,formulas',tableMaxRows:9,tableMaxCols:3,maxChars:2600})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:1600})).ndjson);
for(const [sheetName,range,name] of [['Legend','A24:B29','legend'],['Results','E1:Q6','results'],['Results','E50:Q53','results-middle'],['Results','E99:Q102','results-end'],['Summary','A1:E10','summary'],['Summary','A46:C54','trial-summary'],['QC Feedback','A1:H6','qc'],['QC Feedback',`A${behaviorTitle}:K${behaviorStart+2}`,'behavior'],['QC Feedback',`A${reasonTitle}:E${reasonStart+1}`,'provenance'],['Judge Details','A3:E7','evidence']]) {
  const image=await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(previews,name+'.png'),new Uint8Array(await image.arrayBuffer()));
}
const output=path.join(src,'outputs/01a155af-3583-7582-b58f-357580fa892d/Together_9B_Full_100_Evaluation.xlsx');
await fs.mkdir(path.dirname(output),{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log('Workbook saved: '+output);
