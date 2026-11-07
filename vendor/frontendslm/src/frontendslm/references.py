"""Original deterministic reference fixtures for harness validation, never training data."""
import json

WORKFLOW_JSX = {
    "filter": '''<label>Search<input data-testid="search" value={query} onChange={e=>setQuery(e.target.value)}/></label><ul>{['Atlas','Beacon'].filter(x=>x.toLowerCase().includes(query.toLowerCase())).map(x=><li key={x} data-testid={'item-'+x.toLowerCase()}>{x}</li>)}</ul>''',
    "toggle": '''<button data-testid="task-toggle" aria-pressed={active} onClick={()=>setActive(!active)}>Prepare materials</button><p data-testid="task-status" role="status">{active?'Completed':'Pending'}</p>''',
    "form": '''<form noValidate onSubmit={e=>{e.preventDefault();setStatus(name.trim()&&email.includes('@')?'Confirmed':'Required')}}><label>Name<input data-testid="name" value={name} onChange={e=>setName(e.target.value)}/></label><label>Email<input type="email" data-testid="email" value={email} onChange={e=>setEmail(e.target.value)}/></label><button data-testid="submit">Submit demo</button><p data-testid="form-status" role="status">{status}</p></form>''',
    "tabs": '''<div role="tablist" aria-label="Report view"><button role="tab" aria-selected={!active} data-testid="tab-overview" onClick={()=>setActive(false)}>Overview</button><button role="tab" aria-selected={active} data-testid="tab-details" onClick={()=>setActive(true)}>Details</button></div><section role="tabpanel" data-testid="tab-panel">{active?'Breakdown':'Summary'}</section>''',
    "cart": '''<h3>Field notes edition</h3><p>Fictional product · $12</p><button data-testid="add-item" onClick={()=>setCount(count+1)}>Add item</button><button data-testid="remove-item" onClick={()=>setCount(Math.max(0,count-1))}>Remove item</button><p>Items: <span role="status" data-testid="cart-count">{count}</span></p>''',
    "accordion": '''<button data-testid="faq-toggle" aria-expanded={active} aria-controls="answer" onClick={()=>setActive(!active)}>Getting started</button>{active&&<p id="answer" data-testid="faq-answer">Start with one small step, explore the materials, and practice at your own pace.</p>}''',
    "stepper": '''<button aria-label="Decrease quantity" data-testid="quantity-minus" onClick={()=>setQuantity(Math.max(1,quantity-1))}>−</button><span data-testid="quantity" role="status">{quantity}</span><button aria-label="Increase quantity" data-testid="quantity-plus" onClick={()=>setQuantity(quantity+1)}>+</button>''',
    "theme": '''<button data-testid="theme-toggle" aria-pressed={active} onClick={()=>setActive(!active)}>Change appearance</button><p data-testid="theme-label" role="status">{active?'Night':'Day'}</p><article style={{background:active?'#101f31':'#fff',color:active?'#fff':'#172538',padding:24}}><h3>A different perspective</h3><p>Observe the small details that make everyday places memorable.</p></article>''',
    "sort": '''<label>Search<input data-testid="search" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Order<select data-testid="sort" value={order} onChange={e=>setOrder(e.target.value)}><option value="asc">Lowest first</option><option value="desc">Highest first</option></select></label><ul>{(order==='asc'?['Atlas','Beacon']:['Beacon','Atlas']).filter(x=>x.toLowerCase().includes(query.toLowerCase())).map(x=><li key={x} data-testid="directory-item">{x} · {x==='Atlas'?10:20}</li>)}</ul>''',
    "dialog": '''<button data-testid="open-dialog" onClick={()=>dialog.current?.showModal()}>New note</button><dialog ref={dialog} data-testid="note-dialog" aria-labelledby="dialog-title"><h3 id="dialog-title">New note</h3><label>Note<textarea data-testid="note-input" value={note} onChange={e=>setNote(e.target.value)}/></label><button data-testid="save-note" onClick={()=>{setStatus(note);dialog.current?.close()}}>Save</button></dialog><p data-testid="saved-note" role="status">{status}</p>''',
}


def reference_manifest(case):
    pattern = case["spec"]["interactions"][0]["id"]
    title = case["spec"]["user_goal"].split("interface.")[0].replace("Build a polished single-page ", "").title()
    dark = case["spec"]["style"]["theme"] == "dark"
    background, surface, foreground, muted, accent, on_accent = (
        ("#101922", "#1b2835", "#f5f8fc", "#c0ccd8", "#a3d4cb", "#10211e") if dark else
        ("#f1eee7", "#fffdf8", "#19282f", "#4b5c65", "#194e47", "#ffffff")
    )
    app = '''import {useState,useRef} from 'react';
export default function App(){
 const [query,setQuery]=useState(''); const [active,setActive]=useState(false);
 const [name,setName]=useState(''); const [email,setEmail]=useState('');
 const [status,setStatus]=useState(''); const [count,setCount]=useState(0);
 const [quantity,setQuantity]=useState(1); const [order,setOrder]=useState('asc');
 const [note,setNote]=useState(''); const dialog=useRef<HTMLDialogElement>(null);
 return <><header><a href="#main">FIELDWORK / Demo</a><span>Original reference fixture</span></header>
 <main id="main"><p className="eyebrow">YOUR WORK, CLEARLY ORGANIZED</p><h1>TITLE</h1>
 <p className="intro">A focused space to explore, organize, and take the next step. All information shown is fictional demonstration data.</p>
 <div className="grid"><section className="card"><h2>Workspace</h2>WORKFLOW</section>
 <aside className="card"><h2>At a glance</h2><p className="large">24</p><p>Sample records this month</p><hr/><h3>Next step</h3><p>Use the workspace controls to explore the demo. Changes stay in this page.</p></aside></div>
 <footer>Local demonstration · No external services connected</footer></main></>;
}'''.replace("TITLE", "{" + json.dumps(title) + "}").replace("WORKFLOW", WORKFLOW_JSX[pattern])
    css = f'''@tailwind base; @tailwind components; @tailwind utilities;
:root{{font-family:system-ui,sans-serif;color:{foreground};background:{background};font-synthesis:none}}
*{{box-sizing:border-box}}body{{margin:0}}header{{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:24px 5vw;border-bottom:1px solid {muted}}}
a{{color:inherit}}main{{max-width:1200px;margin:auto;padding:48px 24px}}h1{{font-size:clamp(30px,4.5vw,56px);line-height:1.08;max-width:850px;font-weight:700;letter-spacing:-.035em;margin:16px 0 24px}}h2{{font-size:24px;font-weight:650;margin-bottom:24px}}h3{{font-size:18px;font-weight:650;margin:16px 0}}p{{line-height:1.65}}.intro{{max-width:650px;color:{muted};margin-bottom:40px}}.eyebrow{{font-size:12px;letter-spacing:.14em;color:{muted};font-weight:700}}.grid{{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:24px}}.card{{min-width:0;background:{surface};padding:28px;border-radius:16px}}label{{display:block;margin:16px 0;font-weight:600}}input,select,textarea{{display:block;width:100%;padding:12px;margin-top:8px;color:#172538;background:white;border:1px solid #627685;border-radius:7px}}button{{background:{accent};color:{on_accent};border-radius:7px;padding:12px 18px;margin:6px 8px 6px 0;min-height:44px;font-weight:600}}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{{outline:3px solid #3186dc;outline-offset:4px}}li{{padding:16px 0;border-bottom:1px solid {muted}}}.large{{font-size:64px;font-weight:700}}footer{{padding-top:48px;color:{muted};font-size:13px}}dialog{{max-width:calc(100vw - 32px);width:480px;border:0;border-radius:16px;padding:24px;color:#19282f}}dialog::backdrop{{background:#0008}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}main{{padding:32px 20px}}.card{{padding:20px}}header{{padding:20px}}}}@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important;animation:none!important;transition:none!important}}}}'''
    return {"design_tokens": {"background": background, "surface": surface, "foreground": foreground, "accent": accent},
        "component_tree": ["App", "Header", "Workspace", "Summary"], "files": {"src/App.tsx": app, "src/index.css": css}}
