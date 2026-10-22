// Offline runtime smoke check. This does not replace a browser visual review.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
class Element {
  constructor(name) { this.name=name; this.attrs={}; this.children=[]; this.style={}; this.events={}; this.dataset={}; this.textContent=''; this.classList={toggle:()=>{}}; }
  setAttribute(key,value) { this.attrs[key]=String(value); if(key==='data-id') this.dataset.id=value; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  addEventListener(key,fn) { this.events[key]=fn; }
  querySelectorAll(query) { const result=[]; const walk=e=>{if(query==='.node'&&(e.attrs.class||'').split(' ').includes('node'))result.push(e);e.children.forEach(walk);};this.children.forEach(walk);return result; }
  focus() { this.focused=true; }
  click() { this.clicked=true; if(this.events.click)this.events.click(); }
}
const ids = new Map();
for(const match of html.matchAll(/id="([^"]+)"/g)) ids.set(match[1],new Element('div'));
const tabs=Array.from({length:4},(_,i)=>ids.get('tab-'+i));
let downloadBlob;
const context={console,Blob,setTimeout:fn=>fn(),URL:{createObjectURL:blob=>{downloadBlob=blob;return 'blob:offline-test';},revokeObjectURL:()=>{}},document:{getElementById:id=>{assert(ids.has(id),`Missing element ${id}`);return ids.get(id);},querySelectorAll:query=>{assert.equal(query,'.tab');return tabs;},createElementNS:(_,name)=>new Element(name),createElement:name=>new Element(name)}};
vm.createContext(context);
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
assert.equal(scripts.length,2);
scripts.forEach(script=>vm.runInContext(script,context,{timeout:10000}));
assert.notEqual(ids.get('error').style.display,'block');
const spec=JSON.parse(fs.readFileSync(path.join(__dirname,'diagrams.json'),'utf8'));
for(let i=0;i<4;i++){
  tabs[i].click();
  assert.equal(tabs[i].attrs['aria-selected'],'true');
  const svg=ids.get('canvas').children[0];
  const bounds=svg.attrs.viewBox.split(' ').map(Number);
  assert(bounds.every(Number.isFinite));
  const nodes=ids.get('canvas').querySelectorAll('.node');
  assert.equal(nodes.length,spec.diagrams[i].nodes.length);
  for(const node of nodes){node.click();assert.equal(ids.get('detail-title').textContent,spec.diagrams[i].nodes.find(n=>n.id===node.dataset.id).label);assert(ids.get('detail-copy').textContent.length>5);}
  for(const el of svg.children){if(el.name==='path')assert(!/NaN|Infinity|undefined/.test(el.attrs.d));}
  console.log(`Diagram ${i+1}: ${nodes.length} nodes, automatic bounds ${bounds[2]} × ${bounds[3]}, all node interactions passed`);
}
tabs[3].events.keydown({key:'ArrowRight',preventDefault(){}});
assert.equal(tabs[0].attrs['aria-selected'],'true');
ids.get('next').click();
assert.equal(tabs[1].attrs['aria-selected'],'true');
ids.get('download').click();
downloadBlob.text().then(text=>{
  assert.deepEqual(JSON.parse(text),spec);
  assert(!/<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*["']https?:/i.test(html));
  assert(html.includes("connect-src 'none'"));
  console.log('PASS: tab switching, keyboard navigation, next section, exact JSON export, bundled engine, and no remote page dependencies.');
});
