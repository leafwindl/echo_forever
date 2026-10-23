// Offline DOM/interaction checks, not a browser rendering or visual inspection.
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const file=process.argv[2]||path.join(root,'data/chat-turn-walkthrough/index.html');
const html=fs.readFileSync(file,'utf8');
const ids=new Map(),listeners=new Map();
const decode=s=>s.replace(/&(lt|gt|amp|quot|#39);/g,(_,key)=>({lt:'<',gt:'>',amp:'&',quot:'"','#39':"'"}[key]));
function matches(el,selector){return selector.split(',').some(part=>{part=part.trim();if(part.startsWith('#'))return el.id===part.slice(1);if(part.startsWith('[')){const m=part.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return m&&(m[2]===undefined?el.getAttribute(m[1])!==null:el.getAttribute(m[1])===m[2]);}if(part.startsWith('.'))return part.slice(1).split('.').every(c=>el.className.split(/\s+/).includes(c));return el.tagName.toLowerCase()===part.toLowerCase();});}
class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.parentElement=null;this.children=[];this.attrs={};this.dataset={};this.events={};this.style={};this.className='';this.disabled=false;this.checked=false;this._html='';this._text='';this.classList={toggle:(name,on)=>{const c=new Set(this.className.split(/\s+/).filter(Boolean));on?c.add(name):c.delete(name);this.className=[...c].join(' ');}};}
  setAttribute(key,value){value=String(value);this.attrs[key]=value;if(key==='id'){this.id=value;ids.set(value,this);}if(key==='class')this.className=value;if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;if(key==='checked')this.checked=true;if(key==='disabled')this.disabled=true;}
  getAttribute(key){if(key==='class')return this.className;return this.attrs[key]??null;}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this.clear();this._text=String(value);}
  get value(){return this._value??(this.tagName==='TEXTAREA'?this.textContent:'');}
  set value(value){this._value=String(value);}
  get innerHTML(){return this._html;}
  set innerHTML(value){this.clear();this._html=String(value);parseFragment(this._html,this);}
  clear(){const remove=node=>{if(node.id)ids.delete(node.id);node.children.forEach(remove);};this.children.forEach(remove);this.children=[];this._text='';this._html='';}
  append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}
  appendChild(node){this.append(node);return node;}
  addEventListener(name,fn){(this.events[name]??=[]).push(fn);}
  querySelectorAll(selector){const results=[];const walk=node=>{for(const c of node.children){if(matches(c,selector))results.push(c);walk(c);}};walk(this);return results;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  matches(selector){return matches(this,selector);}
  closest(selector){let n=this;while(n){if(matches(n,selector))return n;n=n.parentElement;}return null;}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
  getContext(){return {font:'',measureText:value=>({width:[...value].reduce((n,c)=>n+(c.charCodeAt(0)>127?12:6),0)})};}
}
function parseFragment(source,parent){const stack=[parent];const tokens=source.match(/<!--[\s\S]*?-->|<\/?[a-zA-Z][^>]*>|[^<]+|</g)||[];for(const token of tokens){if(token.startsWith('<!--'))continue;if(token.startsWith('</')){if(stack.length>1)stack.pop();continue;}if(token.startsWith('<')&&token.length>1){const tag=token.match(/^<([\w-]+)/)?.[1];if(!tag)continue;const el=new Element(tag);for(const a of token.slice(tag.length+1,-1).matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))el.setAttribute(a[1],decode(a[2]??a[3]??a[4]??''));stack.at(-1).append(el);if(!/^(input|br|hr|meta|link|img)$/i.test(tag)&&!token.endsWith('/>'))stack.push(el);}else{const text=new Element('#text');text._text=decode(token);stack.at(-1).append(text);}}}
const body=new Element('body');
parseFragment(html.match(/<body>([\s\S]*?)<script id="case-data"/)[1],body);
const scriptText=id=>{const m=html.match(new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`));assert(m,'Missing script '+id);return m[1];};
const data=JSON.parse(scriptText('case-data'));
const dataElement=new Element('script');dataElement.setAttribute('id','case-data');dataElement.textContent=scriptText('case-data');
const document={getElementById:id=>{assert(ids.has(id),'Missing DOM id: '+id);return ids.get(id);},createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelector:s=>body.querySelector(s),addEventListener:(name,fn)=>{(listeners.get(name)||listeners.set(name,[]).get(name)).push(fn);}};
let copied='';
const ctx={console,document,location:{hash:''},history:{replaceState(){}},navigator:{clipboard:{writeText:async value=>{copied=value;}}},setTimeout:()=>1,clearTimeout(){}};
ctx.window=ctx;ctx.self=ctx;vm.createContext(ctx);
for(const id of ['dagre-bundle','walkthrough-core','walkthrough-ui'])vm.runInContext(scriptText(id),ctx,{timeout:10000,filename:id+'.js'});
const C=ctx.ChatWalkthrough,U=ctx.ChatWalkthroughUI;
const find=(selector)=>{const e=body.querySelector(selector);assert(e,'Missing selector: '+selector);return e;};
async function dispatch(name,element,extra={}){const event={target:element,preventDefault(){this.prevented=true;},...extra};for(const fn of element.events[name]||[])await fn(event);for(const fn of listeners.get(name)||[])await fn(event);return event;}
async function click(selector){const el=find(selector);assert(!el.disabled,'Disabled control: '+selector);await dispatch('click',el);}
async function change(id,checked){const el=ids.get(id);assert(el,id);el.checked=checked;await dispatch('change',el);}
function validateGraph(g){assert(g.nodes.length<=12);const nodes=new Set(g.nodes.map(n=>n.id)),edges=new Set(),pairs=new Set();assert.equal(nodes.size,g.nodes.length);for(const e of g.edges){assert(nodes.has(e.from)&&nodes.has(e.to));assert.notEqual(e.from,e.to);assert(!edges.has(e.id));edges.add(e.id);const pair=e.from+'|'+e.to;assert(!pairs.has(pair));pairs.add(pair);}const walk=v=>{if(v&&typeof v==='object')for(const[k,x]of Object.entries(v)){assert(!['x','y','width','height','path','marker','points'].includes(k));walk(x);}};walk(g);}
(async()=>{
  validateGraph(data.graph);assert.equal(data.graph.nodes.length,10);
  assert.equal(ids.get('flow').querySelectorAll('.flow-node').length,10,'Dagre rendered every semantic node');
  assert.equal(ids.get('flow').querySelectorAll('polyline').length,9);
  assert(ids.get('flow').getAttribute('viewBox').split(' ').map(Number).every(Number.isFinite));
  assert.equal(C.current.content.length,19);assert.equal(C.replies.length,2);assert.equal(data.case.tools.length,0);
  assert.equal(data.case.run.step_count,1);assert.equal(data.case.turn.message_count,1);
  for(const ref of Object.values(data.refs)){const text=fs.readFileSync(path.join(root,ref.file),'utf8').replaceAll('\r\n','\n');assert(text.split('\n')[ref.line-1].includes(ref.symbol),ref.file);assert(text.includes(ref.excerpt));assert.equal(crypto.createHash('sha256').update(text).digest('hex'),ref.sha256);}
  for(let i=0;i<10;i++){U.setStep(i);assert.equal(ids.get('step-title').textContent,data.steps[i].headline);for(const tab of ['process','data','source','check']){await click(`[data-tab="${tab}"]`);assert.equal(ids.get('tab-'+tab).getAttribute('aria-selected'),'true');assert(ids.get('view').textContent.length>70);if(tab==='source')assert.equal(ids.get('view').querySelectorAll('.source-card').length,data.steps[i].refs.length);if(tab==='data')assert.doesNotThrow(()=>JSON.parse(find('.json-panel').querySelector('pre').textContent));}}
  U.setStep(0);await click('[data-action="prior-chat"]');assert.equal(ids.get('prior-chat').querySelectorAll('.chat-bubble').length,9);await click('[data-action="prior-chat"]');assert.equal(ids.get('prior-chat').innerHTML,'');
  await click('#next');assert.equal(C.state.step,1);await click('[data-action="retry"]');assert(C.packet('accepted').replayed);assert.equal(ids.get('retry-result').textContent.includes('不新增'),true);
  U.setStep(2);await click('[data-action="lab-empty"]');await click('[data-action="lab-run"]');assert(ids.get('lab-result').textContent.includes('422'));
  await click('[data-action="lab-long"]');await click('[data-action="lab-run"]');assert(ids.get('lab-result').textContent.includes('400'));
  await click('[data-action="lab-normal"]');await change('lab-auth',false);await click('[data-action="lab-run"]');assert(ids.get('lab-result').textContent.includes('401'));
  await change('lab-auth',true);await change('lab-uuid',false);await click('[data-action="lab-run"]');assert(ids.get('lab-result').textContent.includes('422'));
  await change('lab-uuid',true);await click('[data-action="lab-run"]');assert(ids.get('lab-result').textContent.includes('202'));
  U.setStep(4);for(const m of data.materials){await click(`[data-material="${m.id}"]`);assert(find('.material-info').textContent.includes(m.acquisition));await click('[data-action="material-source"]');assert.equal(C.state.tab,'source');assert.equal(ids.get('view').querySelectorAll('.source-card').length,m.refs.length);await click('[data-tab="process"]');}
  U.setStep(5);assert.equal(C.state.revealed,1);for(let i=1;i<data.blocks.length;i++)await click('[data-action="add-block"]');assert.equal(find('[data-action="add-block"]').disabled,true);assert.equal(find('.stack').querySelectorAll('.stack-row').length,23);assert.equal(C.state.selectedBlock,'current');
  for(const b of data.blocks){await click(`[data-block="${b.id}"]`);assert(find('.inspection-head').textContent.includes(b.title));}
  await change('show-unknown',false);assert.equal(C.contextBlocks().length,17);await click('[data-action="reset-blocks"]');assert.equal(C.state.revealed,1);await click('[data-action="all-blocks"]');assert.equal(C.state.selectedBlock,'current');
  U.setStep(6);await click('[data-tab="data"]');await change('include-history',false);assert.equal(C.messageList().length,8);assert.equal(C.messageList().at(-1).content,C.current.content);assert(C.messageList().slice(0,-1).every(m=>m.role==='system'));await change('include-history',true);await change('include-unknown',true);assert.equal(C.messageList().length,23);await click('[data-action="copy-json"]');assert.deepEqual(JSON.parse(copied).messages,JSON.parse(JSON.stringify(C.messageList())));
  await click('[data-tab="process"]');for(let n=0;n<3;n++){await click('[data-action="tool-next"]');assert.equal(ids.get('tool-branch').open,true);}let pair=JSON.parse(find('.tool-body').querySelector('.json-panel').querySelector('pre').textContent);assert.equal(pair.length,2);assert.equal(pair[0].tool_calls[0].id,pair[1].tool_call_id);assert.equal(JSON.parse(pair[1].content).status,'completed');await change('tool-invalid',true);pair=JSON.parse(find('.tool-body').querySelector('.json-panel').querySelector('pre').textContent);assert.equal(JSON.parse(pair[1].content).error_code,'invalid_tool_arguments');assert.equal(data.toolSchema.function.parameters.properties.day_offset.maximum,7);await click('[data-action="tool-reset"]');assert.equal(C.state.toolStep,0);
  U.setStep(9);assert.equal(ids.get('view').querySelectorAll('.chat-bubble').length,3);for(let i=0;i<3;i++){await click(`[data-quiz="${i}"]`);assert(ids.get('quiz-'+i).textContent.length>15);}await click('#prev');assert.equal(C.state.step,8);await dispatch('keydown',ids.get('view'),{key:'ArrowLeft'});assert.equal(C.state.step,7);await dispatch('keydown',ids.get('view'),{key:'ArrowRight'});assert.equal(C.state.step,8);await click('#restart');assert.equal(C.state.step,0);assert.equal(C.state.revealed,1);assert.equal(C.state.includeUnknown,true);
  for(let i=0;i<10;i++){const node=ids.get('flow').querySelectorAll('.flow-node')[i];await dispatch('click',node);assert.equal(C.state.step,i);assert.equal(node.getAttribute('aria-pressed'),'true');}
  assert(!/<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*["']https?:/i.test(html));
  assert(!/\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/.test(scriptText('walkthrough-core')+scriptText('walkthrough-ui')));
  assert(html.includes("connect-src 'none'"));assert(!html.includes('__CASE_DATA__'));
  assert(!/phone_[a-f0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}/.test(html));
  console.log(`PASS: 10 steps × 4 views; ${Object.keys(data.refs).length} current source anchors; 10 Dagre nodes / 9 edges; 23-position assembly; validation/retry/material-source/tool-result/quiz/keyboard/copy interactions; offline resource and private-ID checks.`);
  console.log('Verification used an offline DOM harness. Browser screenshots and device rendering were not available.');
})().catch(error=>{console.error(error);process.exitCode=1;});
