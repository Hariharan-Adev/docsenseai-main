import { Keyboard } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { matchPath, useLocation, useNavigate } from 'react-router-dom'
import BookmarksModal from '../components/BookmarksModal'
import ChatArea from '../components/ChatArea'
import ConfigurationPage from '../components/ConfigurationPage'
import DashboardAnalytics from '../components/DashboardAnalytics'
import DocumentPreviewModal from '../components/DocumentPreviewModal'
import LibraryPage from '../components/LibraryPage'
import ProjectsPage from '../components/ProjectsPage'
import SettingsModal from '../components/SettingsModal'
import Sidebar from '../components/Sidebar'
import UploadDocumentsModal from '../components/UploadDocumentsModal'
import { Button } from '../components/ui/Button'
import { useApp } from '../context/AppContext'
import MainLayout from '../layouts/MainLayout'

const negativeToastPattern = /\b(?:cannot|cancelled|cleared|deleted|error|expired|failed|failure|removed|unable|wrong)\b/i
const positiveToastPattern = /\b(?:bookmarked|copied|enabled|liked|saved|started|success|successful|successfully|uploaded)\b/i

function toastColor(message: string) {
  if (negativeToastPattern.test(message)) {
    return 'bg-gradient-to-br from-red-600 to-rose-500 shadow-[0_10px_30px_rgba(220,38,38,.28)]'
  }

  if (positiveToastPattern.test(message)) {
    return 'bg-gradient-to-br from-emerald-600 to-green-500 shadow-[0_10px_30px_rgba(5,150,105,.28)]'
  }

  return 'bg-gradient-to-br from-blue-600 to-indigo-500 shadow-[0_10px_30px_rgba(37,99,235,.28)]'
}

// Converts supported browser URLs into the existing dashboard selection state.
function dashboardRoute(pathname: string) {
  const folder = matchPath('/projects/:projectId/folders/:folderId', pathname)
  if (folder) return { view: 'project' as const, projectId: folder.params.projectId ?? null, folderId: folder.params.folderId ?? null }
  const project = matchPath('/projects/:projectId', pathname)
  if (project) return { view: 'project' as const, projectId: project.params.projectId ?? null, folderId: null }
  if (pathname === '/projects') return { view: 'projects' as const, projectId: null, folderId: null }
  if (pathname === '/documents') return { view: 'library' as const, projectId: null, folderId: null }
  if (pathname === '/configuration' || matchPath('/configuration/:integrationId', pathname)) return { view: 'configuration' as const }
  if (pathname === '/' || pathname === '/chat') return { view: 'chat' as const }
  return null
}

export default function Dashboard(){
  const {setSidebarOpen,setView,setSelectedProjectId,setSelectedFolderId,setSelectedCollectionId,setSelectedDocument,view,toast,newChat}=useApp()
  const location=useLocation()
  const navigate=useNavigate()
  const [upload,setUpload]=useState(false)
  const [settings,setSettings]=useState(false)
  const [help,setHelp]=useState(false)
  const [bookmarks,setBookmarks]=useState(false)

  useEffect(()=>{
    const route=dashboardRoute(location.pathname)
    if(!route)return
    setHelp(false)
    setSettings(false)
    setView(route.view)
    if('projectId' in route){
      setSelectedProjectId(route.projectId ?? null)
      setSelectedFolderId(route.folderId ?? null)
      setSelectedCollectionId(null)
      setSelectedDocument(null)
    }
  },[location.pathname,setSelectedCollectionId,setSelectedDocument,setSelectedFolderId,setSelectedProjectId,setView])

  useEffect(()=>{
    const shortcut=(event:KeyboardEvent)=>{
      if(!(event.ctrlKey||event.metaKey))return
      if(event.key.toLowerCase()==='k'){event.preventDefault();document.getElementById('library-search')?.focus()}
      if(event.key.toLowerCase()==='n'){event.preventDefault();newChat()}
      if(event.key==='/'){event.preventDefault();setSettings(false);setHelp(true)}
    }
    window.addEventListener('keydown',shortcut)
    return()=>window.removeEventListener('keydown',shortcut)
  },[newChat])

  return <MainLayout>
    <motion.div initial={{opacity:0}} animate={{opacity:1}} transition={{duration:.3}} className="flex min-w-0 flex-1">
      <Sidebar onClose={()=>setSidebarOpen(false)} onNewChat={()=>{newChat();navigate('/chat')}} onUpload={()=>navigate('/documents')} onProjects={()=>navigate('/projects')} onSettings={()=>{setHelp(false);if(view==='configuration')setView('dashboard');setSettings(true)}} onConfiguration={()=>{setHelp(false);setSettings(false);navigate('/configuration')}} onHelp={()=>{setSettings(false);setHelp(true)}}/>
      {help?<div className="h-screen min-w-0 flex-1 overflow-y-auto bg-[#f8faff] p-6">
        <div className="mx-auto max-w-4xl">
          <h1 className="mb-6 text-xl font-semibold text-slate-900">Help &amp; keyboard shortcuts</h1>
          <div className="rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50 p-4"><div className="flex items-center gap-2 text-blue-700"><Keyboard size={18}/><p className="text-sm font-bold">Move faster with shortcuts</p></div></div>
          <div className="mt-4 space-y-2">{[['Ctrl + K','Focus policy search'],['Ctrl + N','Start a new chat'],['Ctrl + /','Open help'],['Esc','Close the active modal'],['Enter','Send a question'],['Shift + Enter','Add a new line']].map(([keys,label])=><div key={keys} className="flex items-center justify-between rounded-xl border border-[#eef2f7] bg-white p-3 shadow-[0_3px_12px_rgba(37,99,235,.03)]"><span className="text-xs text-slate-600">{label}</span><kbd className="rounded-md border border-blue-100 bg-blue-50 px-2 py-1 text-[10px] font-semibold text-blue-600">{keys}</kbd></div>)}</div>
          <Button className="mt-5 w-full" onClick={()=>setHelp(false)}>Got it</Button>
        </div>
      </div>:settings?<SettingsModal open onClose={()=>setSettings(false)}/>:view==='library'||view==='project'?<LibraryPage onUpload={()=>setUpload(true)}/>:view==='projects'?<ProjectsPage/>:view==='chat'?<ChatArea onUpload={()=>setUpload(true)}/>:view==='configuration'?<ConfigurationPage routeIntegrationId={matchPath('/configuration/:integrationId',location.pathname)?.params.integrationId} onNavigate={integrationId=>navigate(integrationId?`/configuration/${integrationId}`:'/configuration')} onBack={()=>navigate(-1)}/>:<DashboardAnalytics/>}
    </motion.div>
    <UploadDocumentsModal open={upload} onClose={()=>setUpload(false)}/>
    <BookmarksModal open={bookmarks} onClose={()=>setBookmarks(false)}/>
    <DocumentPreviewModal/>
    <AnimatePresence>{toast&&<motion.div role="status" initial={{opacity:0,y:15}} animate={{opacity:1,y:0}} exit={{opacity:0,y:10}} className={`fixed bottom-6 left-1/2 z-[90] -translate-x-1/2 rounded-xl px-4 py-3 text-xs font-medium text-white ${toastColor(toast)}`}>{toast}</motion.div>}</AnimatePresence>
  </MainLayout>
}
