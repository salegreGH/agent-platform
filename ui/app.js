
const { useEffect, useRef, useState } = React;

function Badge({children}){
  return React.createElement("span",{className:"px-2 py-0.5 rounded-full text-xs bg-slate-800 border border-slate-700"},children);
}

function App(){
  const [msg, setMsg] = useState("");
  const [chat, setChat] = useState([]);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState({agents:[], skills:[], proposals:[], configs:{}});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const endRef = useRef(null);

  async function refreshState(){
    const r = await fetch("/api/state");
    const j = await r.json();
    setState(j);
  }

  useEffect(()=>{ refreshState(); },[]);
  useEffect(()=>{ endRef.current?.scrollIntoView({behavior:"smooth"}); },[chat,busy]);

  async function saveKey(){
    const r = await fetch("/api/settings/openai_key",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key: apiKey})});
    const j = await r.json();
    setChat(c=>[...c,{role:"system",content: j.ok ? "✅ API key guardada" : ("❌ "+(j.error||"error"))}]);
    await refreshState();
  }

  async function send(){
    const text = msg.trim();
    if(!text || busy) return;
    setMsg("");
    setBusy(true);
    setChat(c=>[...c,{role:"user",content:text}]);

    try{
      const r = await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:text})});
      const j = await r.json();
      if(j.reply) setChat(c=>[...c,{role:"assistant",content:j.reply}]);
      (j.cards||[]).forEach(card=> setChat(c=>[...c,{role:"assistant",content:"```json\n"+JSON.stringify(card,null,2)+"\n```"}]));
    }catch(e){
      setChat(c=>[...c,{role:"system",content:"❌ Error: "+String(e)}]);
    }finally{
      setBusy(false);
      await refreshState();
    }
  }

  async function approveProposal(id){
    setBusy(true);
    try{
      const r = await fetch("/api/proposals/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({proposal_id:id})});
      const j = await r.json();
      setChat(c=>[...c,{role:"system",content:j.ok ? `✅ Proposal ${id} aplicada` : `❌ No s'ha pogut aplicar: ${j.error||JSON.stringify(j)}`}]);
    }finally{
      setBusy(false);
      await refreshState();
    }
  }

  return React.createElement("div",{className:"h-screen flex"},
    // Sidebar
    React.createElement("div",{className:"w-80 border-r border-slate-800 bg-slate-900/40 p-4 flex flex-col gap-4"},
      React.createElement("div",{className:"flex items-center justify-between"},
        React.createElement("div",null,
          React.createElement("div",{className:"text-lg font-semibold"},"Agent Platform"),
          React.createElement("div",{className:"text-xs text-slate-400"},"v4 · local orchestrator")
        ),
        React.createElement("button",{onClick:()=>setSettingsOpen(o=>!o),className:"px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm"},"Settings")
      ),

      settingsOpen && React.createElement("div",{className:"rounded-xl border border-slate-800 p-3 bg-slate-950/40"},
        React.createElement("div",{className:"text-sm font-medium mb-2"},"OpenAI API key"),
        React.createElement("input",{value:apiKey,onChange:e=>setApiKey(e.target.value),type:"password",placeholder:"sk-...",className:"w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800"}),
        React.createElement("button",{onClick:saveKey,className:"mt-2 w-full px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm"},"Guardar"),
        React.createElement("div",{className:"mt-2 text-xs text-slate-400"},"Guardada a Windows Credential Manager (keyring).")
      ),

      React.createElement("div",{className:"rounded-xl border border-slate-800 p-3 bg-slate-950/30"},
        React.createElement("div",{className:"flex items-center justify-between mb-2"},
          React.createElement("div",{className:"text-sm font-medium"},"Agents"),
          React.createElement(Badge,null,String(state.agents.length))
        ),
        React.createElement("div",{className:"flex flex-col gap-2 max-h-48 overflow-auto"},
          state.agents.map(a => React.createElement("div",{key:a.id,className:"p-2 rounded-lg bg-slate-900 border border-slate-800"},
            React.createElement("div",{className:"flex items-center justify-between"},
              React.createElement("div",{className:"text-sm font-semibold"},a.name),
              React.createElement("span",{className:"text-xs "+(a.status==="ready"?"text-emerald-400":"text-amber-400")},a.status)
            ),
            React.createElement("div",{className:"text-xs text-slate-400"},a.purpose)
          ))
        )
      ),

      React.createElement("div",{className:"rounded-xl border border-slate-800 p-3 bg-slate-950/30"},
        React.createElement("div",{className:"flex items-center justify-between mb-2"},
          React.createElement("div",{className:"text-sm font-medium"},"Skills"),
          React.createElement(Badge,null,String(state.skills.length))
        ),
        React.createElement("div",{className:"flex flex-col gap-2 max-h-40 overflow-auto"},
          state.skills.map(s => React.createElement("div",{key:s.id,className:"p-2 rounded-lg bg-slate-900 border border-slate-800"},
            React.createElement("div",{className:"text-sm font-semibold"},s.title),
            React.createElement("div",{className:"text-xs text-slate-400"},"action: "+s.action)
          ))
        )
      ),

      React.createElement("div",{className:"rounded-xl border border-slate-800 p-3 bg-slate-950/30"},
        React.createElement("div",{className:"flex items-center justify-between mb-2"},
          React.createElement("div",{className:"text-sm font-medium"},"Proposals"),
          React.createElement(Badge,null,String(state.proposals.length))
        ),
        React.createElement("div",{className:"flex flex-col gap-2 max-h-40 overflow-auto"},
          state.proposals.map(p => React.createElement("div",{key:p.proposal_id,className:"p-2 rounded-lg bg-slate-900 border border-slate-800"},
            React.createElement("div",{className:"flex items-center justify-between"},
              React.createElement("div",{className:"text-sm font-semibold"},p.title),
              React.createElement("span",{className:"text-xs text-amber-400"},p.status)
            ),
            React.createElement("div",{className:"text-xs text-slate-400 truncate"},p.file_path),
            React.createElement("button",{disabled:busy,onClick:()=>approveProposal(p.proposal_id),className:"mt-2 w-full px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-sm disabled:opacity-50"},"Approve")
          )),
          !state.proposals.length && React.createElement("div",{className:"text-xs text-slate-500"},"Cap proposta pendent.")
        )
      ),

      React.createElement("div",{className:"text-xs text-slate-500 mt-auto"},"Tip: prova “Digues-me l'últim email d'Outlook”.")
    ),

    // Main
    React.createElement("div",{className:"flex-1 flex flex-col"},
      React.createElement("div",{className:"border-b border-slate-800 p-4 bg-slate-950/40"},
        React.createElement("div",{className:"text-sm text-slate-300"},"Xat amb l'orquestrador local (LLM + tools)")
      ),
      React.createElement("div",{className:"flex-1 overflow-auto p-6 space-y-4"},
        chat.map((m,i)=> React.createElement("div",{key:i,className:"max-w-3xl "+(m.role==="user"?"ml-auto":"")},
          React.createElement("div",{className:"rounded-2xl px-4 py-3 border "+(
            m.role==="user" ? "bg-blue-600/20 border-blue-500/30" :
            m.role==="assistant" ? "bg-slate-900 border-slate-800" :
            "bg-amber-600/10 border-amber-500/20"
          )},
            React.createElement("div",{className:"text-xs text-slate-400 mb-1"},m.role),
            React.createElement("div",{className:"whitespace-pre-wrap text-sm"},m.content)
          )
        )),
        busy && React.createElement("div",{className:"max-w-3xl"},
          React.createElement("div",{className:"rounded-2xl px-4 py-3 border bg-slate-900 border-slate-800"},
            React.createElement("div",{className:"text-xs text-slate-400 mb-1"},"assistant"),
            React.createElement("div",{className:"text-sm text-slate-300"},"Pensant…")
          )
        ),
        React.createElement("div",{ref:endRef})
      ),
      React.createElement("div",{className:"border-t border-slate-800 p-4 bg-slate-950/40"},
        React.createElement("div",{className:"max-w-4xl mx-auto flex gap-3"},
          React.createElement("textarea",{
            value:msg,onChange:e=>setMsg(e.target.value),
            onKeyDown:(e)=>{ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); send(); } },
            placeholder:"Escriu una ordre… (Enter per enviar, Shift+Enter nova línia)",
            className:"flex-1 h-12 resize-none px-4 py-3 rounded-xl bg-slate-900 border border-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600/50"
          }),
          React.createElement("button",{disabled:busy,onClick:send,className:"px-5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50"},"Enviar")
        )
      )
    )
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(App));
