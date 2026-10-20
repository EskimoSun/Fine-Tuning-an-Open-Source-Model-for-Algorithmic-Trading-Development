import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire(process.env.ARTIFACT_TOOL_ROOT
  ? path.join(process.env.ARTIFACT_TOOL_ROOT, 'package.json') : import.meta.url);
const {FileBlob, SpreadsheetFile} = await import(require.resolve('@oai/artifact-tool'));
const [template, payloadPath, outputPath, previewDir] = process.argv.slice(2);
const data = JSON.parse(await fs.readFile(payloadPath, 'utf8'));
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
if (previewDir) {
  await fs.mkdir(previewDir, {recursive:true});
  const before = await workbook.render({sheetName:'Results',range:'A1:Q6',scale:1,format:'png'});
  await fs.writeFile(path.join(previewDir,'before.png'),new Uint8Array(await before.arrayBuffer()));
}
if (process.env.QC_EXCEL_INSPECT_ONLY === '1') process.exit(0);
const results = workbook.worksheets.getItem('Results');
const legend = workbook.worksheets.getItem('Legend');
const summary = workbook.worksheets.getItem('Summary');
const first = 3, last = first + data.prompts.length - 1;
// Keep all 100 prompt rows, existing model columns, and human-entered values.
results.getRange(`F${first}:N${last}`).clear({applyTo:'contents'});
results.getRange(`Q${first}:Q${last}`).clear({applyTo:'contents'});
const rowOf = new Map(data.prompts.map((p,i)=>[p.id,first+i]));
for (const row of data.baseline) {
  const r = rowOf.get(row.prompt_id);
  results.getRange(`I${r}:K${r}`).values = [[row.compile_errors,row.runtime_errors,row.fidelity]];
  results.getRange(`Q${r}`).values = [[row.note]];
  results.getRange(`Q${r}`).format.wrapText = true;
}
results.getRange(`E${first}:E${last}`).format.wrapText = true;
results.getRange(`E${first}:E${last}`).format.columnWidth = 68;
results.getRange(`Q${first}:Q${last}`).format.columnWidth = 65;
const baselineNotes = new Map(data.baseline.map(r=>[r.prompt_id,r.note]));
for (const [index,prompt] of data.prompts.entries()) {
  const lines=Math.max(Math.ceil(prompt.prompt.length/72),Math.ceil((baselineNotes.get(prompt.id)||'').length/68));
  results.getRange(`A${first+index}:Q${first+index}`).format.rowHeight=Math.max(52,lines*13+12);
}
for (const r of [5,11,18,22]) legend.getRange(`B${r}`).format.wrapText = true;
legend.getRange('B8').values = [['Original model outputs stay in Results. QC-feedback repairs and their judge scores are reported separately on QC Feedback and Judge Details. Blank means not evaluated.']];
legend.getRange('B9').values = [['Compile errors: build diagnostic error-line estimate; 0 when QC reports BuildSuccess. Python attribute errors can still fail at runtime.']];
legend.getRange('B11').values = [[`Prompt fidelity uses ${data.judge_model}, with the original 1-5 rubric and evidence for eight requirement dimensions.`]];
legend.getRange('B18').values = [['Human scores remain editable. A review flag is not a human score. Repaired-candidate scores must not be entered in the raw Qwen base column.']];
legend.getRange('B22').values = [['Qwen generation uses temperature 0. Opus 5.5 uses default sampling and an 8192-token thinking-plus-answer budget. Outputs, exact source hashes, QC IDs, and raw judge replies are saved in the snapshot.']];
legend.getRange('A24:B29').values = [
  ['Snapshot','10 original Qwen candidates, 3 QC-feedback candidates, and 3 real Claude judgments. The other 90 original prompt rows remain blank.'],
  ['Model columns','Fable and Qwen tuned columns are blank because no real candidate executions for those model groups are included. Gold template executions are not Fable generations.'],
  ['Behavior metrics','Filled orders and closed trades are different counts. F1 uses a 60-second tolerance; interval error is in seconds; DTW compares normalized daily equity with a one-observation window.'],
  ['Date mismatch','RSI requests Q4 2024 but its Gold starts in September. Counts are shown with different-window warnings; similarity metrics are withheld.'],
  ['Review','ROC retains the original Claude score of 4/5. An analyst flags its monthly schedule for review even though Claude did not.'],
  ['Sources',data.snapshot+'/baseline_random10/qc_summary.json; '+data.snapshot+'/repairs/<prompt_id>/history.json; '+data.snapshot+'/judge_trial3/scoring/qwen_qc_feedback_trial/<prompt_id>.json']
];
legend.getRange('A24:A29').format.font = {name:'Arial',size:10,bold:true};
legend.getRange('B3:B29').format.wrapText = true;
legend.getRange('B3:B29').format.columnWidth = 110;
legend.getRange('A3:B29').format.rowHeight = 42;
legend.getRange('A24:B29').format.font.name = 'Arial';

// Existing summary layout is retained. Correct affected missing-data counts.
for (const [column,[ce,re,fi]] of Object.entries({B:['F','G','H'],C:['I','J','K'],D:['L','M','N']})) {
  summary.getRange(`${column}9`).formulas = [[`=IFERROR(COUNTIFS(Results!${ce}${first}:${ce}${last},0,Results!${re}${first}:${re}${last},0,Results!${re}${first}:${re}${last},"<>")/COUNT(Results!${re}${first}:${re}${last}),"-")`]];
}
summary.getRange('A12').values = [['Judge check (judge vs human, Qwen base)']];
summary.getRange('A14').values = [['Mean absolute judge-human fidelity gap']];
summary.getRange('A15').values = [['Share where judge and human agree exactly']];
summary.getRange('A16').values = [['Human agreement is unavailable until both judge and human scores exist for the same original candidate.']];
summary.getRange('B13').formulas = [[`=SUMPRODUCT((Results!O${first}:O${last}="Y")*ISNUMBER(Results!P${first}:P${last})*ISNUMBER(Results!K${first}:K${last}))`]];
summary.getRange('B14').formulas = [[`=IFERROR(SUMPRODUCT((Results!O${first}:O${last}="Y")*ISNUMBER(Results!P${first}:P${last})*ISNUMBER(Results!K${first}:K${last})*ABS(Results!K${first}:K${last}-Results!P${first}:P${last}))/B13,"-")`]];
summary.getRange('B15').formulas = [[`=IFERROR(SUMPRODUCT((Results!O${first}:O${last}="Y")*ISNUMBER(Results!P${first}:P${last})*ISNUMBER(Results!K${first}:K${last})*(Results!K${first}:K${last}=Results!P${first}:P${last}))/B13,"-")`]];

function sheetNamed(name) {
  try { return workbook.worksheets.getItem(name); }
  catch { return workbook.worksheets.add(name); }
}
const feedback = sheetNamed('QC Feedback');
const details = sheetNamed('Judge Details');
feedback.getUsedRange()?.clear({applyTo:'all'});
details.getUsedRange()?.clear({applyTo:'all'});
function header(sheet,address,values) {
  const range = sheet.getRange(address);
  range.values=[values];
  range.format={fill:'#1F3A5F',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:38};
}
feedback.getRange('A1').values=[['Qwen with QC feedback: separate experiment']];
feedback.getRange('A1').format.font={name:'Arial',size:14,bold:true};
header(feedback,'A3:H3',['Prompt ID','Generation model','Repair rounds','Compile errors','Runtime errors','Fidelity (1-5)','QC status','Review required']);
feedback.getRange(`A4:H${3+data.feedback.length}`).values=data.feedback;
feedback.getRange('A10').values=[['Behavior diagnostics against Gold']];
header(feedback,'A12:K12',['Prompt ID','Candidate filled orders','Gold filled orders','Candidate closed trades','Gold closed trades','Fill F1','Interval MAE (seconds)','Equity DTW','Position agreement','Behavior status','Comparison limits']);
feedback.getRange(`A13:K${12+data.behavior.length}`).values=data.behavior;
feedback.getRange('A19').values=[['Judge reasons and execution provenance']];
header(feedback,'A21:F21',['Prompt ID','Strategy','Judge reason','Review notes','QC project ID','QC backtest ID']);
feedback.getRange(`A22:F${21+data.reasons.length}`).values=data.reasons;
feedback.getRange('A1:K24').format.font.name='Arial';
feedback.getRange('A4:H6').format.rowHeight=38;
feedback.getRange('A13:K15').format.rowHeight=70;
feedback.getRange('A13:K15').format.wrapText=true;
feedback.getRange('A22:F24').format.rowHeight=230;
feedback.getRange('A22:F24').format.wrapText=true;
feedback.getRange('A22:F24').format.verticalAlignment='top';
const widths=[52,26,62,36,24,42,20,20,18,20,64];
for(let c=0;c<widths.length;c++) feedback.getRangeByIndexes(0,c,24,1).format.columnWidth=widths[c];
feedback.getRange('F13:F15').setNumberFormat('0.000');
feedback.getRange('G13:G15').setNumberFormat('#,##0.0');
feedback.getRange('H13:H15').setNumberFormat('0.000000');
feedback.getRange('I13:I15').setNumberFormat('0.0%');
feedback.getRange('A4:H6').format.wrapText=true;
feedback.getRange('C4:H6').format.horizontalAlignment='center';
feedback.freezePanes.freezeRows(3);
feedback.getRange('G4:G6').conditionalFormats.addCustom('G4="runtime_error"',{fill:'#FCE4D6',font:{color:'#9C0006'}});

details.getRange('A1').values=[['Claude prompt-adherence evidence']];
details.getRange('A1').format.font={name:'Arial',size:14,bold:true};
header(details,'A3:F3',['Prompt ID','Dimension','Requested requirement','Judge status','Candidate line evidence','Source JSON']);
details.getRange(`A4:F${3+data.details.length}`).values=data.details;
details.getRange(`A4:F${3+data.details.length}`).format={font:{name:'Arial',size:10},wrapText:true,verticalAlignment:'top'};
for(const [c,width] of [48,24,62,20,110,70].entries()) details.getRangeByIndexes(0,c,27,1).format.columnWidth=width;
for(const [index,row] of data.details.entries()) {
  const widths=[48,24,62,20,110,70];
  const lines=Math.max(...row.map((value,i)=>Math.ceil(String(value).length/(widths[i]*1.1))));
  details.getRange(`A${index+4}:F${index+4}`).format.rowHeight=Math.max(36,lines*14+10);
}
details.freezePanes.freezeRows(3);

header(summary,'A46:C46',['QC-feedback metric','Value','Scope']);
summary.getRange('A47:A51').values=[['Candidates evaluated'],['Completed backtests'],['Candidates judged'],['Average fidelity (1-5)'],['Review required']];
summary.getRange('B47:B51').formulas=[['=COUNTA(\'QC Feedback\'!A4:A6)'],['=COUNTIFS(\'QC Feedback\'!G4:G6,"completed")'],['=COUNT(\'QC Feedback\'!F4:F6)'],['=IFERROR(AVERAGE(\'QC Feedback\'!F4:F6),"-")'],['=COUNTIFS(\'QC Feedback\'!H4:H6,"Y")']];
summary.getRange('C47:C51').values=[['Separate from original Qwen base'],['Successful execution only'],[data.judge_model],['Unchanged raw judge scores'],['Judge flags plus analyst review']];
summary.getRange('B50').setNumberFormat('0.00');
summary.getRange('A46:C51').format.font.name='Arial';
summary.getRange('A12:A16').format.wrapText=true;
summary.getRange('A12:A16').format.rowHeight=36;
summary.getRange('A1:A51').format.columnWidth=58;
summary.getRange('B1:E51').format.columnWidth=28;
summary.getRange('C47:C51').format.wrapText=true;
summary.getRange('A47:C51').format.rowHeight=34;
// Verify a live summary dependency, then restore the original saved judge score.
const originalScore=feedback.getRange('F4').values[0][0];
const originalMean=summary.getRange('B50').values[0][0];
feedback.getRange('F4').values=[[1]];
workbook.recalculate();
const changedMean=summary.getRange('B50').values[0][0];
const expectedMean=originalMean+(1-originalScore)/data.feedback.length;
if (Math.abs(changedMean-expectedMean)>1e-10) throw new Error('Feedback summary did not recalculate after an input change');
feedback.getRange('F4').values=[[originalScore]];
workbook.recalculate();
if (summary.getRange('B50').values[0][0]!==originalMean) throw new Error('Original judge scores were not restored');
console.log((await workbook.inspect({kind:'table',range:'Summary!A46:C51',include:'values,formulas',tableMaxRows:6,tableMaxCols:3,maxChars:2200})).ndjson);
console.log((await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:2000})).ndjson);
if (previewDir) {
  for (const [sheetName,range,name] of [['Legend','A1:B11','legend'],['Legend','A24:B29','legend-sources'],['Results','E1:Q7','results'],['Summary','A1:E16','summary'],['Summary','A46:C51','feedback-summary'],['QC Feedback','A1:H6','feedback'],['QC Feedback','A10:K16','behavior'],['QC Feedback','A19:F24','reasons'],['Judge Details','A3:E6','judge-details']]) {
    const preview=await workbook.render({sheetName,range,scale:1,format:'png'});
    await fs.writeFile(path.join(previewDir,name+'.png'),new Uint8Array(await preview.arrayBuffer()));
  }
}
await fs.mkdir(path.dirname(outputPath),{recursive:true});
await (await SpreadsheetFile.exportXlsx(workbook)).save(outputPath);
console.log('Workbook updated: '+outputPath);
