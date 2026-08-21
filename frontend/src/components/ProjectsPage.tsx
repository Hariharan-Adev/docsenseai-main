import { FolderKanban, Menu, MoreHorizontal, Pin, Plus, Search, Settings, Share2, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent, type MouseEvent } from 'react'
import { useApp } from '../context/AppContext'
import { deleteProject as deleteProjectApi, type ProjectRecord } from '../services/api'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

type ProjectFilter = 'all' | 'created' | 'shared'

// Keep project timestamps compact and readable while tolerating legacy API values.
function projectUpdatedAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

// The projects index keeps unsupported project-management actions local and explicit.
export default function ProjectsPage() {
  const { projects, createProject, selectedProjectId, setSelectedProjectId, setSelectedFolderId, setSelectedCollectionId, setSelectedDocument, setSidebarOpen, setView, showToast } = useApp()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ProjectFilter>('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [creating, setCreating] = useState(false)
  const [actionsProjectId, setActionsProjectId] = useState<string | null>(null)
  const [pinnedProjectIds, setPinnedProjectIds] = useState<Set<string>>(() => new Set())
  const [settingsProject, setSettingsProject] = useState<ProjectRecord | null>(null)
  const [settingsName, setSettingsName] = useState('')
  const [instructions, setInstructions] = useState('')
  const [memory, setMemory] = useState('default')
  const [libraryEnabled, setLibraryEnabled] = useState(true)
  const [deleteProject, setDeleteProject] = useState<ProjectRecord | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deletedProjectIds, setDeletedProjectIds] = useState<Set<string>>(() => new Set())

  const visibleProjects = useMemo(() => {
    // The current API returns owner-created projects only, so Shared stays empty.
    if (filter === 'shared') return []
    const query = search.trim().toLowerCase()
    return projects
      .filter(project => !deletedProjectIds.has(project.id))
      .filter(project => !query || `${project.name} ${project.description ?? ''}`.toLowerCase().includes(query))
      .sort((a, b) => Number(pinnedProjectIds.has(b.id)) - Number(pinnedProjectIds.has(a.id)))
  }, [deletedProjectIds, filter, pinnedProjectIds, projects, search])

  useEffect(() => {
    if (actionsProjectId === null) return
    const closeMenu = () => setActionsProjectId(null)
    document.addEventListener('pointerdown', closeMenu)
    return () => document.removeEventListener('pointerdown', closeMenu)
  }, [actionsProjectId])

  // Reset nested filters so every project opens at its root workspace.
  const openProject = (projectId: string) => {
    setSelectedProjectId(projectId)
    setSelectedFolderId(null)
    setSelectedCollectionId(null)
    setSelectedDocument(null)
    setActionsProjectId(null)
    setView('project')
  }

  // Create through the existing context API, then follow the established open flow.
  const submitCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = projectName.trim()
    if (!name || creating) return
    setCreating(true)
    try {
      const project = await createProject(name)
      setProjectName('')
      setCreateOpen(false)
      openProject(project.id)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to create project.')
    } finally {
      setCreating(false)
    }
  }

  // Keep the overflow control independent from the clickable project row.
  const toggleActions = (event: MouseEvent<HTMLButtonElement>, projectId: string) => {
    event.stopPropagation()
    setActionsProjectId(current => current === projectId ? null : projectId)
  }

  // Pinning is a view preference until project metadata APIs expose it.
  const togglePin = (projectId: string) => {
    setPinnedProjectIds(previous => {
      const next = new Set(previous)
      if (next.has(projectId)) next.delete(projectId)
      else next.add(projectId)
      return next
    })
    setActionsProjectId(null)
  }

  // Settings remain editable locally without implying unsupported persistence.
  const openSettings = (project: ProjectRecord) => {
    setSettingsProject(project)
    setSettingsName(project.name)
    setInstructions('')
    setMemory('default')
    setLibraryEnabled(true)
    setActionsProjectId(null)
  }

  const saveSettings = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!settingsName.trim()) return
    setSettingsProject(null)
    showToast('Project settings changes are not available yet.')
  }

  // Keep the confirmation open on failure and hide the deleted project immediately on success.
  const confirmDelete = async () => {
    if (!deleteProject || deleting) return
    const projectId = deleteProject.id
    setDeleting(true)
    try {
      await deleteProjectApi(projectId)
      setDeletedProjectIds(previous => new Set(previous).add(projectId))
      setDeleteProject(null)
      if (selectedProjectId === projectId) {
        setSelectedProjectId(null)
        setSelectedFolderId(null)
        setSelectedCollectionId(null)
        setSelectedDocument(null)
        setView('projects')
      }
      showToast('Project deleted.')
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to delete project.')
    } finally {
      setDeleting(false)
    }
  }

  return <section className="min-w-0 flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 sm:px-7 sm:py-7">
    <div className="mx-auto max-w-[1000px]">
      <div className="mb-5 flex items-center gap-3">
        <button type="button" onClick={() => setSidebarOpen(true)} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-slate-500 shadow-sm hover:bg-blue-50 hover:text-blue-600 lg:hidden" aria-label="Open sidebar"><Menu size={20} /></button>
        <h1 className="min-w-0 flex-1 text-2xl font-bold tracking-[-.035em] text-slate-900 sm:text-[28px]">Projects</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}><Plus size={16} />New Project</Button>
      </div>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1 sm:max-w-sm"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search projects" className="h-10 w-full rounded-xl border border-[#e6ecf5] bg-white pl-9 pr-3 text-[12px] outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100/60" /></div>
        <div className="flex gap-1 overflow-x-auto">
          {([['all', 'All'], ['created', 'Created by you'], ['shared', 'Shared with you']] as const).map(([value, label]) => <button key={value} type="button" onClick={() => setFilter(value)} className={`shrink-0 rounded-lg px-3 py-2 text-[11px] font-semibold ${filter === value ? 'bg-blue-50 text-blue-700' : 'text-slate-500 hover:bg-white hover:text-slate-800'}`}>{label}</button>)}
        </div>
      </div>

      {visibleProjects.length > 0 ? <div className="space-y-2">
        <div className="hidden grid-cols-[minmax(0,1fr)_140px_44px] gap-3 border-b border-[#e6ecf5] px-3 pb-2 text-[10px] font-semibold uppercase tracking-[.08em] text-slate-400 sm:grid"><span>Name</span><span>Modified</span><span /></div>
        {visibleProjects.map(project => <div key={project.id} role="button" tabIndex={0} onClick={() => openProject(project.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') openProject(project.id) }} className="relative grid cursor-pointer grid-cols-[40px_minmax(0,1fr)_44px] items-center gap-3 rounded-xl border border-[#eef2f7] bg-white px-3 py-2.5 text-left hover:border-blue-100 sm:grid-cols-[40px_minmax(0,1fr)_140px_44px]">
          <span className="relative grid h-9 w-9 place-items-center rounded-lg bg-blue-50 text-blue-600"><FolderKanban size={17} />{pinnedProjectIds.has(project.id) && <Pin size={10} className="absolute -right-1 -top-1 fill-blue-600" />}</span>
          <span className="min-w-0"><span className="block truncate text-[12px] font-semibold text-slate-800">{project.name}</span><span className="mt-0.5 block text-[10px] text-slate-400 sm:hidden">Modified {projectUpdatedAt(project.updated_at)}</span></span>
          <span className="hidden text-[11px] text-slate-500 sm:block">{projectUpdatedAt(project.updated_at)}</span>
          <button type="button" onPointerDown={event => event.stopPropagation()} onClick={event => toggleActions(event, project.id)} className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-blue-50 hover:text-blue-600" aria-label={`Actions for ${project.name}`} aria-expanded={actionsProjectId === project.id}><MoreHorizontal size={16} /></button>
          {actionsProjectId === project.id && <div onPointerDown={event => event.stopPropagation()} onClick={event => event.stopPropagation()} className="absolute right-3 top-11 z-20 w-48 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg" role="menu">
            <button type="button" onClick={() => togglePin(project.id)} className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-[11px] font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-600"><Pin size={14} />{pinnedProjectIds.has(project.id) ? 'Unpin Project' : 'Pin Project'}</button>
            <button type="button" onClick={() => { setActionsProjectId(null); showToast('Project sharing is not available yet.') }} className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-[11px] font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-600"><Share2 size={14} />Share</button>
            <button type="button" onClick={() => openSettings(project)} className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-[11px] font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-600"><Settings size={14} />Project Settings</button>
            <button type="button" onClick={() => { setActionsProjectId(null); setDeleteProject(project) }} className="flex h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-[11px] font-medium text-red-600 hover:bg-red-50"><Trash2 size={14} />Delete Project</button>
          </div>}
        </div>)}
      </div> : <div className="py-10 text-center"><FolderKanban className="mx-auto text-slate-300" size={26} /><p className="mt-2 text-[12px] font-semibold text-slate-600">{filter === 'shared' ? 'No projects have been shared with you.' : search ? 'No matching projects.' : 'No projects yet.'}</p>{filter !== 'shared' && !search && <button type="button" onClick={() => setCreateOpen(true)} className="mt-3 text-[11px] font-semibold text-blue-600 hover:text-blue-700">Create your first project</button>}</div>}
    </div>

    <Modal open={createOpen} onClose={() => { if (!creating) { setCreateOpen(false); setProjectName('') } }} title="Create project">
      <form onSubmit={submitCreateProject} className="flex w-full flex-col gap-5">
        <div className="w-full space-y-2"><label htmlFor="project-name" className="block text-xs font-semibold text-slate-700">Project name</label><input id="project-name" autoFocus value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="Enter project name" className="field h-11 w-full" maxLength={100} /><p className="text-[11px] leading-5 text-slate-500">Projects keep related chats, documents, and files together in one place.</p></div>
        <div className="flex w-full justify-end gap-2"><Button type="button" variant="secondary" size="sm" disabled={creating} onClick={() => { setCreateOpen(false); setProjectName('') }}>Cancel</Button><Button type="submit" size="sm" disabled={!projectName.trim() || creating}>{creating ? 'Creating...' : 'Create project'}</Button></div>
      </form>
    </Modal>

    <Modal open={settingsProject !== null} onClose={() => setSettingsProject(null)} title="Project settings">
      <form onSubmit={saveSettings} className="flex w-full flex-col gap-5">
        <div className="w-full space-y-2"><label htmlFor="settings-project-name" className="block text-xs font-semibold text-slate-700">Project Name</label><input id="settings-project-name" value={settingsName} onChange={event => setSettingsName(event.target.value)} className="field h-11 w-full" maxLength={100} /></div>
        <div className="w-full space-y-2"><label htmlFor="project-instructions" className="block text-xs font-semibold text-slate-700">Instructions</label><textarea id="project-instructions" value={instructions} onChange={event => setInstructions(event.target.value)} rows={4} className="field w-full resize-y py-3" placeholder="Add instructions for work in this project" /><p className="text-[10px] leading-4 text-slate-400">Set context and customize how responses behave in this project.</p></div>
        <div className="w-full space-y-2"><label htmlFor="project-memory" className="block text-xs font-semibold text-slate-700">Memory</label><select id="project-memory" value={memory} onChange={event => setMemory(event.target.value)} className="field h-11 w-full"><option value="default">Default memory</option></select><p className="text-[10px] leading-4 text-slate-400">Default memory follows your current Docsense conversation behavior.</p></div>
        <label className="flex w-full items-start justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50/60 p-3"><span><span className="block text-xs font-semibold text-slate-700">Library Access</span><span className="mt-1 block text-[10px] leading-4 text-slate-400">{libraryEnabled ? 'Enabled' : 'Disabled'}</span></span><input type="checkbox" checked={libraryEnabled} onChange={event => setLibraryEnabled(event.target.checked)} className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" /></label>
        <div className="flex w-full flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between"><Button type="button" variant="danger" size="sm" className="self-start" onClick={() => { if (settingsProject) setDeleteProject(settingsProject); setSettingsProject(null) }}><Trash2 size={14} />Delete project</Button><div className="ml-auto flex gap-2"><Button type="button" variant="secondary" size="sm" onClick={() => setSettingsProject(null)}>Cancel</Button><Button type="submit" size="sm" disabled={!settingsName.trim()}>Save</Button></div></div>
      </form>
    </Modal>

    <Modal open={deleteProject !== null} onClose={() => { if (!deleting) setDeleteProject(null) }} title="Delete project?">
      <p className="text-[12px] leading-5 text-slate-600">This would delete <span className="font-semibold text-slate-800">{deleteProject?.name}</span>. This action cannot be undone.</p>
      <div className="mt-6 flex justify-end gap-2"><Button type="button" variant="secondary" size="sm" disabled={deleting} onClick={() => setDeleteProject(null)}>Cancel</Button><Button type="button" variant="danger" size="sm" disabled={deleting} onClick={confirmDelete}>{deleting ? 'Deleting…' : 'Delete project'}</Button></div>
    </Modal>
  </section>
}
