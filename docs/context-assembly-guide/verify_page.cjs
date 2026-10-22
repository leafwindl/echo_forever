// Offline structural and interaction smoke checks; no browser visual review implied.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const ids = new Map();
class Element {
  constructor(tag) { this.tag=tag;this.attrs={};this.children=[];this.style={};this.dataset={};this.events={};this.className='';this.hidden=false;this.value='';this.classList={toggle:(name,on)=>{const c=new Set(this.className.split(' ').filter(Boolean));on?c.add(name):c.delete(name);this.className=[...c].join(' ');}}; }
  set id(value) { this._id=value;ids.set(value,this); }
  get id() { return this._id; }
  set textContent(value) { this._text=String(value);this.children=[]; }
  get textContent() { return (this._text||'')+this.children.map(c=>c.textContent).join(''); }
  setAttribute(key,value) {this.attrs[key]=String(value);if(key==='class')this.className=value;if(key==='data-id')this.dataset.id=value;}
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this._text='';this.children=[...items];}
  addEventListener(key,fn) {this.events[key]=fn;}
  querySelectorAll(query) {const result=[];const walk=e=>{if((query==='.node'&&e.className.split(' ').includes('node'))||e.tag===query)result.push(e);e.children.forEach(walk);};this.children.forEach(walk);return result;}
  querySelector(query) {return this.querySelectorAll(query)[0]||null;}
  focus() {this.focused=true;}
  scrollIntoView() {this.scrolled=true;}
  click() {const event={target:this,preventDefault(){}};if(this.events.click)this.events.click(event);if(this.onclick)this.onclick(event);}
}
for(const match of html.matchAll(/\bid="([^"]+)"/g)) {const e=new Element('div');e.id=match[1];}
ids.get('error').hidden=true; // Matches the initial hidden attribute in the HTML.
let blobDownload, downloadName;
const context={console,Blob,setTimeout:fn=>fn(),URL:{createObjectURL:blob=>{blobDownload=blob;return 'blob:offline';},revokeObjectURL(){}},document:{getElementById:id=>{assert(ids.has(id),'Missing DOM id: '+id);return ids.get(id);},createElement:tag=>{const e=new Element(tag);if(tag==='a'){const click=e.click.bind(e);e.click=()=>{downloadName=e.download;click();};}return e;},createElementNS:(_,tag)=>new Element(tag),createTextNode:text=>{const e=new Element('#text');e.textContent=text;return e;}}};
vm.createContext(context);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
assert.equal(scripts.length,2);
scripts.forEach(script=>vm.runInContext(script,context,{timeout:15000}));
assert.equal(ids.get('error').hidden,true,ids.get('error').textContent);
const evaluate=code=>vm.runInContext(code,context,{timeout:10000});
const data=JSON.parse(evaluate('JSON.stringify(GUIDE)'));
assert.equal(data.sources.length,16);
assert.equal(ids.get('source-list').children.length,16);
assert.equal(ids.get('example-list').children.length,data.examples.length);
assert.equal(ids.get('budget-bars').children.length,11);
assert(ids.get('budget-total').textContent.includes('5,259'));
assert.equal(evaluate("renderSourceFilter('没有这种材料-888')"),0);
assert(evaluate("renderSourceFilter('summary_message_id')")>0);
assert(evaluate("renderSourceFilter('default_persona.py')")>0);
evaluate('renderSourceFilter()');
for(const r of Object.values(data.references)) {
  const file=path.resolve(__dirname,'../..',r.file);
  const text=fs.readFileSync(file,'utf8');
  assert(text.split(/\r?\n/)[r.line-1].includes(r.symbol),r.file+':'+r.line);
  assert.equal(crypto.createHash('sha256').update(text.replaceAll('\r\n','\n')).digest('hex'),r.sha256);
  assert(text.replaceAll('\r\n','\n').includes(r.excerpt));
}
for(let index=0;index<data.diagrams.length;index++) {
  ids.get('diagram-tab-'+index).click();
  const diagram=data.diagrams[index];
  assert.equal(ids.get('diagram-tab-'+index).attrs['aria-selected'],'true');
  const nodes=ids.get('canvas').querySelectorAll('.node');
  assert.equal(nodes.length,diagram.nodes.length);
  const svg=ids.get('canvas').children[0];
  const bounds=svg.attrs.viewBox.split(' ').map(Number);
  assert(bounds.every(Number.isFinite));
  assert(bounds[2]>0&&bounds[3]>0);
  for(const node of nodes){node.click();const expected=diagram.nodes.find(n=>n.id===node.dataset.id);assert.equal(ids.get('node-title').textContent,expected.label);assert(ids.get('node-description').textContent.length>12);assert(ids.get('node-source').href.startsWith('#source-'));}
  svg.querySelectorAll('path').forEach(p=>assert(!/NaN|undefined|Infinity/.test(p.attrs.d)));
  console.log(`Diagram ${index+1}: ${nodes.length} nodes; engine bounds ${Math.ceil(bounds[2])} x ${Math.ceil(bounds[3])}; all selections passed.`);
}
ids.get('diagram-tab-2').events.keydown({key:'ArrowRight',preventDefault(){}});
assert.equal(ids.get('diagram-tab-0').attrs['aria-selected'],'true');
const keys=['preferences','memory','summary','history','sticker','toolRound'];
for(let bits=0;bits<64;bits++){
  keys.forEach((key,i)=>{const control=ids.get('toggle-'+key);control.checked=Boolean(bits&(1<<i));control.events.change({target:control});});
  const visible=JSON.parse(evaluate('JSON.stringify(activeLayers())'));
  assert.equal(ids.get('stack-list').children.length,visible.length);
  assert.equal(visible[0].id,'agent');
  assert.equal(visible.findIndex(l=>l.id==='safety'),bits&16?2:1);
  assert.equal(visible.some(l=>l.id==='preferences'),Boolean(bits&1));
  assert.equal(visible.some(l=>l.id==='memory'),Boolean(bits&2));
  assert.equal(visible.some(l=>l.id==='summary'),Boolean(bits&4));
  assert.equal(visible.filter(l=>l.id.startsWith('history-')).length,bits&8?2:0);
  assert.equal(visible[visible.length-1].id,bits&32?'result':'current');
  for(const button of ids.get('stack-list').children){button.click();assert.equal(button.attrs['aria-pressed'],'true');assert(ids.get('layer-origin').textContent.length>15);const layer=data.layers.find(l=>l.id===button.dataset.layer);assert.equal(ids.get('layer-preview').textContent,layer.preview);}
  assert.doesNotThrow(()=>JSON.parse(ids.get('request-preview').textContent));
}
for(const name of ['basic','rich','sticker','tool'])ids.get('preset-'+name).click();
assert.equal(ids.get('layer-role').textContent,'tool');
const list=ids.get('stack-list');list.children[0].events.keydown({key:'End',preventDefault(){}});
assert.equal(ids.get('layer-role').textContent,'tool');
const demo=JSON.parse(evaluate('JSON.stringify(requestDemo())'));
const messages=demo.请求示意.messages;
assert.equal(messages.at(-2).tool_calls[0].id,messages.at(-1).tool_call_id);
assert.equal(messages.at(-3).role,'user');
ids.get('source-search').value='没有匹配';evaluate("renderSourceFilter('没有匹配')");
evaluate("jumpToSource('memory')");
assert.equal(ids.get('source-memory').hidden,false);
assert.equal(ids.get('source-memory').open,true);
assert.equal(ids.get('source-search').value,'');
for(const source of data.sources){evaluate(`jumpToSource(${JSON.stringify(source.id)})`);assert(ids.get('source-'+source.id).querySelector('summary').focused);}
assert(!/<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*["']https?:/i.test(html));
assert(!/\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/.test(scripts.join('\n')));
assert(html.includes("connect-src 'none'"));
const specification=JSON.parse(fs.readFileSync(path.join(__dirname,'diagrams.json'),'utf8'));
assert.deepEqual(specification,{diagrams:data.diagrams});
function checkNoGeometry(value){if(value&&typeof value==='object')for(const [key,item]of Object.entries(value)){assert(!['x','y','width','height','path','marker','points'].includes(key));checkNoGeometry(item);}}
checkNoGeometry(specification);
(async()=>{
  ids.get('export-diagrams').click();assert.equal(downloadName,'echo-context-diagrams.json');assert.deepEqual(JSON.parse(await blobDownload.text()),specification);
  ids.get('export-request').click();assert.equal(downloadName,'echo-context-demo.json');assert.deepEqual(JSON.parse(await blobDownload.text()),demo);
  console.log(`PASS: 64 material combinations, all diagrams/nodes/layers, presets, keyboard controls, 16 source jumps, ${Object.keys(data.references).length} current source references, paired tool messages, JSON downloads, and no remote resources.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
