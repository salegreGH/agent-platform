const { useEffect, useMemo, useRef, useState } = React;

function App(){
  const [msg, setMsg] = useState("");
  const [chat, setChat] = useState([]);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState({agents:[], skills:[], proposals:[], tasks:[], runs:[], forms:[], connectors:{}, browser_sessions:[]});
  const [sidebarTab, setSidebarTab] = useState("chat");
  const [wizard, setWizard] = useState(null);
  const endRef = useRef(null);

  const tabItems = useMemo(()=>([
    {id:"chat",label:"Chat"},{id:"runs",label:"Runs",count:(state.runs||[]).length},{id:"browser",label:"Browser",count:(state.browser_sessions||[]).length},{id:"connectors",label:"Connectors",count:Object.keys(state.connectors||{}).length}
  ]),[state]);

  async function refreshState(){ const r = await fetch('/api/state'); setState(await r.json()); }
  useEffect(()=>{ refreshState(); },[]);
  useEffect(()=>{ endRef.current?.scrollIntoView({behavior:"smooth"}); },[chat,busy,wizard]);

  async function handleAction(action, runId){
    if(action.kind === 'open_browser'){
      await fetch('/core/browser/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'https://outlook.office.com/mail/', run_id: runId||wizard?.run_id})});
      setSidebarTab('browser');
      await refreshState();
      return;
    }
    if(action.kind === 'mark_login_done'){
      const rid = runId || wizard?.run_id;
      if(!rid) return;
      const r = await fetch(`/core/run/${rid}/mark_login_done`,{method:'POST'});
      const j = await r.json();
      if(j.reply) setChat(c=>[...c,{role:'assistant',content:j.reply,actions:j.actions||[]}]);
      if(j.wizard) setWizard({...j.wizard, run_id: rid});
      await refreshState();
      return;
    }
    if(action.kind === 'switch_browser'){
      setMsg('no es viable');
      return;
    }
    if(action.kind === 'open_device_login' && action.url){
      window.open(action.url, '_blank');
    }
  }

  async function send(){
    if(!msg.trim() || busy) return;
    const text = msg.trim(); setMsg(""); setBusy(true); setChat(c=>[...c,{role:"user",content:text}]);
    try{
      const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
      const j = await r.json();
      if(j.reply) setChat(c=>[...c,{role:"assistant",content:j.reply,actions:j.actions||[],run:j.run}]);
      if(j.wizard) setWizard({...j.wizard, run_id: j.run?.run_id});
    } finally { setBusy(false); refreshState(); }
  }

  function renderMessage(m, i){
    return React.createElement('div',{key:i,className:m.role==='user'?'text-right':''},
      React.createElement('div',{className:'inline-block px-3 py-2 rounded border border-slate-700 text-sm whitespace-pre-wrap'},m.content),
      (m.actions||[]).length>0 && React.createElement('div',{className:'mt-2 flex gap-2 justify-end'},
        m.actions.map(a=>React.createElement('button',{key:a.id,onClick:()=>handleAction(a,m.run?.run_id),className:'px-2 py-1 rounded bg-blue-600 text-xs'},a.label))
      )
    );
  }

  function browserWizard(){
    if(!wizard?.show) return null;
    return React.createElement('div',{className:'p-3 rounded border border-amber-700 bg-amber-950/30 text-sm mb-3'},
      React.createElement('div',{className:'font-semibold mb-1'},'Browser Setup Wizard'),
      React.createElement('div',{className:'text-xs mb-2'},`Estado: ${wizard.status_text || wizard.state}`),
      React.createElement('div',{className:'flex gap-2'},
        React.createElement('button',{className:'px-2 py-1 rounded bg-indigo-600 text-xs',onClick:()=>handleAction({kind:'open_browser'}, wizard.run_id)},'Abrir navegador'),
        React.createElement('button',{className:'px-2 py-1 rounded bg-emerald-600 text-xs',onClick:()=>handleAction({kind:'mark_login_done'}, wizard.run_id)},'Ya hice login')
      )
    );
  }

  function panel(){
    if(sidebarTab==='runs') return React.createElement('div',{},(state.runs||[]).map(r=>React.createElement('div',{key:r.run_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${r.run_id} · ${r.metadata?.task_state||r.status}`)));
    if(sidebarTab==='browser') return React.createElement('div',{},(state.browser_sessions||[]).map(s=>React.createElement('div',{key:s.session_id,className:'p-2 border border-slate-800 rounded mb-2 text-xs'},`${s.session_id} · ${s.status}${s.login_detected?' · login detectat':''}`)));
    if(sidebarTab==='connectors') return React.createElement('pre',{className:'text-xs whitespace-pre-wrap'},JSON.stringify(state.connectors,null,2));
    return React.createElement('div',{className:'text-xs text-slate-400'},'Escriu una petició a Chat.');
  }

  return React.createElement('div',{className:'h-screen flex'},
    React.createElement('div',{className:'w-80 p-3 border-r border-slate-800 bg-slate-900/40'},
      React.createElement('div',{className:'text-lg font-semibold mb-3'},'Agent Platform v5'),
      React.createElement('div',{className:'grid grid-cols-2 gap-1 mb-3'},tabItems.map(t=>React.createElement('button',{key:t.id,onClick:()=>setSidebarTab(t.id),className:'px-2 py-1 rounded border border-slate-700 text-xs'},`${t.label}${t.count!==undefined?` (${t.count})`:''}`))),
      panel()
    ),
    React.createElement('div',{className:'flex-1 flex flex-col'},
      React.createElement('div',{className:'flex-1 overflow-auto p-6 space-y-3'},browserWizard(), chat.map(renderMessage), busy && React.createElement('div',null,'Pensant...'), React.createElement('div',{ref:endRef})),
      React.createElement('div',{className:'p-3 border-t border-slate-800 flex gap-2'},React.createElement('textarea',{value:msg,onChange:e=>setMsg(e.target.value),className:'flex-1 h-12 bg-slate-900 border border-slate-700 rounded p-2',placeholder:'Demana l\'últim email...'}),React.createElement('button',{onClick:send,className:'px-4 bg-blue-600 rounded'},'Enviar'))
    )
  );
}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
