const { useEffect, useMemo, useRef, useState } = React;

function Badge({children}){ return React.createElement("span",{className:"px-2 py-0.5 rounded-full text-xs bg-slate-800 border border-slate-700"},children); }

function App(){
  const [msg, setMsg] = useState("");
  const [chat, setChat] = useState([]);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState({agents:[], skills:[], proposals:[], tasks:[], runs:[], forms:[], connectors:{}, browser_sessions:[]});
  const [sidebarTab, setSidebarTab] = useState("chat");
  const [formValues, setFormValues] = useState({});
  const [logsText, setLogsText] = useState("");
  const endRef = useRef(null);

  const tabItems = useMemo(()=>([
    {id:"chat",label:"Chat"},{id:"tasks",label:"Tasks",count:state.tasks.length},{id:"runs",label:"Runs",count:state.runs.length},{id:"agents",label:"Agents",count:state.agents.length},
    {id:"connectors",label:"Connectors",count:Object.keys(state.connectors||{}).length},{id:"browser",label:"Browser",count:(state.browser_sessions||[]).length},{id:"skills",label:"Skills",count:state.skills.length},
    {id:"proposals",label:"Proposals",count:state.proposals.filter(p=>p.status==='proposed').length},{id:"forms",label:"Forms",count:state.forms.length},{id:"tests",label:"Tests"},
    {id:"evolve",label:"Evolve"},{id:"files",label:"Files"},{id:"logs",label:"Logs"},{id:"settings",label:"Settings"}
  ]),[state]);

  async function refreshState(){ const r = await fetch('/api/state'); setState(await r.json()); }
  async function refreshLogs(){ const r = await fetch('/api/logs'); const j = await r.json(); setLogsText(j.content||""); }
  useEffect(()=>{ refreshState(); },[]);
  useEffect(()=>{ endRef.current?.scrollIntoView({behavior:"smooth"}); },[chat,busy]);

  async function send(){
    if(!msg.trim() || busy) return;
    const text = msg.trim(); setMsg(""); setBusy(true); setChat(c=>[...c,{role:"user",content:text}]);
    try{ const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})}); const j = await r.json(); if(j.reply) setChat(c=>[...c,{role:"assistant",content:j.reply}]); }
    finally{ setBusy(false); refreshState(); }
  }

  async function approveProposal(id){ await fetch('/api/proposals/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:id})}); refreshState(); }

  async function submitForm(form){
    await fetch(`/api/forms/${form.form_id}/submit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values:formValues})});
    setFormValues({}); refreshState();
  }

  async function uploadFile(e){
    const file = e.target.files?.[0]; if(!file) return;
    const asB64 = await new Promise((resolve)=>{ const r = new FileReader(); r.onload=()=>resolve(String(r.result).split(',')[1]||''); r.readAsDataURL(file); });
    await fetch('/api/uploads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name, content_base64:asB64})});
    refreshState();
  }

  function panel(){
    if(sidebarTab==="tasks") return React.createElement('div',{},state.tasks.map(t=>React.createElement('div',{key:t.task_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${t.goal} · ${t.status}`)));
    if(sidebarTab==="agents") return React.createElement('div',{},state.agents.map(a=>React.createElement('div',{key:a.id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${a.name} · ${a.purpose}`)));
    if(sidebarTab==="runs") return React.createElement('div',{},(state.runs||[]).map(r=>React.createElement('div',{key:r.run_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${r.goal} · ${r.status} · steps: ${(r.steps||[]).length}`)));
    if(sidebarTab==="browser") return React.createElement('div',{},(state.browser_sessions||[]).map(s=>React.createElement('div',{key:s.session_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${s.session_id} · ${s.status}${s.pause_reason?` · ${s.pause_reason}`:''}`)));

    if(sidebarTab==="connectors") return React.createElement('pre',{className:'text-xs whitespace-pre-wrap'},JSON.stringify(state.connectors,null,2));
    if(sidebarTab==="skills") return React.createElement('div',{},state.skills.map(s=>React.createElement('div',{key:s.id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},s.title)));
    if(sidebarTab==="proposals") return React.createElement('div',{},state.proposals.map(p=>React.createElement('div',{key:p.proposal_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},
      React.createElement('div',null,`${p.title} · ${p.status}`),
      p.status==='proposed' && React.createElement('button',{onClick:()=>approveProposal(p.proposal_id),className:'mt-1 px-2 py-1 bg-emerald-600 rounded'},'Approve & Deploy')
    )));
    if(sidebarTab==="forms") return React.createElement('div',{},state.forms.map(f=>React.createElement('div',{key:f.form_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},
      React.createElement('div',{className:'font-semibold mb-2'},`${f.form_type} · ${f.status}`),
      (f.schema.fields||[]).map(field=>React.createElement('input',{key:field.key,placeholder:field.question,className:'w-full mb-1 p-1 bg-slate-900 border border-slate-700 rounded',value:formValues[field.key]||'',onChange:e=>setFormValues(v=>({...v,[field.key]:e.target.value}))})),
      React.createElement('button',{onClick:()=>submitForm(f),className:'px-2 py-1 bg-blue-600 rounded'},'Guardar i reintentar')
    )));
    if(sidebarTab==="files") return React.createElement('div',{},React.createElement('input',{type:'file',onChange:uploadFile,className:'text-xs'}),React.createElement('div',{className:'text-xs text-slate-400 mt-2'},'Els adjunts es guarden al workspace.'));
    if(sidebarTab==="tests") return React.createElement('div',{className:'text-xs text-slate-300'},'Regression dashboard pendent de connectors e2e.');
    if(sidebarTab==="evolve") return React.createElement('div',{className:'text-xs text-slate-300'},`Pipeline d'evolució activa: proposals → approve → tests → release/rollback.`);
    if(sidebarTab==="logs") return React.createElement('div',{},React.createElement('button',{onClick:refreshLogs,className:'px-2 py-1 bg-slate-700 rounded text-xs mb-2'},'Refresh'),React.createElement('pre',{className:'text-xs whitespace-pre-wrap'},logsText));
    if(sidebarTab==="settings") return React.createElement('div',{className:'text-xs text-slate-300'},`Workspace: ${state.configs?.workspace||'-'}`);
    return React.createElement('div',{className:'text-xs text-slate-400'},'Mode control plane actiu.');
  }

  return React.createElement('div',{className:'h-screen flex'},
    React.createElement('div',{className:'w-96 p-3 border-r border-slate-800 bg-slate-900/40'},
      React.createElement('div',{className:'text-lg font-semibold mb-3'},'Agent Platform v5'),
      React.createElement('div',{className:'grid grid-cols-3 gap-1 mb-3'},tabItems.map(t=>React.createElement('button',{key:t.id,onClick:()=>setSidebarTab(t.id),className:'px-2 py-1 rounded border border-slate-700 text-xs'},`${t.label}${t.count!==undefined?` (${t.count})`:''}`))),
      panel()
    ),
    React.createElement('div',{className:'flex-1 flex flex-col'},
      React.createElement('div',{className:'flex-1 overflow-auto p-6 space-y-3'},chat.map((m,i)=>React.createElement('div',{key:i,className:m.role==='user'?'text-right':''},React.createElement('div',{className:'inline-block px-3 py-2 rounded border border-slate-700 text-sm'},m.content))), busy && React.createElement('div',null,'Pensant...'), React.createElement('div',{ref:endRef})),
      React.createElement('div',{className:'p-3 border-t border-slate-800 flex gap-2'},React.createElement('textarea',{value:msg,onChange:e=>setMsg(e.target.value),className:'flex-1 h-12 bg-slate-900 border border-slate-700 rounded p-2',placeholder:'Explica la tasca...'}),React.createElement('button',{onClick:send,className:'px-4 bg-blue-600 rounded'},'Enviar'))
    )
  );
}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
