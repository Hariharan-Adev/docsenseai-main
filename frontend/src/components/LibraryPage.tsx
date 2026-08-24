import { Archive, Check, ChevronDown, Edit2, FileText, FolderOpen, Menu, Plus, Search, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import type { PolicyDocument } from '../types'
import DocumentDeleteModal from './DocumentDeleteModal'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

function relativeDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(date)
  target.setHours(0, 0, 0, 0)
  const days = Math.floor((today.getTime() - target.getTime()) / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  return date.toLocaleDateString()
}

export default function LibraryPage({ onUpload }: { onUpload: () => void }) {
  const { documents, collections, projects, folders, selectedProjectId, setSelectedProjectId, selectedFolderId, setSelectedFolderId, selectedCollectionId, setSelectedCollectionId, setSelectedDocument, createFolder, renameFolder, deleteFolder, removeDocument, setSidebarOpen, showToast } = useApp()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [editingFolderId, setEditingFolderId] = useState<string | null>(null)
  const [editingFolderName, setEditingFolderName] = useState('')
  const [documentToDelete, setDocumentToDelete] = useState<PolicyDocument | null>(null)
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [folderToDelete, setFolderToDelete] = useState<{ id: string; name: string } | null>(null)
  const [isDeletingFolder, setIsDeletingFolder] = useState(false)
  const [folderMenuId, setFolderMenuId] = useState<string | null>(null)
  const deleteTriggerRef = useRef<HTMLButtonElement | null>(null)
  const headerSelectAllRef = useRef<HTMLInputElement | null>(null)
  const toolbarSelectAllRef = useRef<HTMLInputElement | null>(null)
  const filtered = useMemo(() => [...documents]
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .filter(document => selectedCollectionId === null || document.collectionId === selectedCollectionId)
    .filter(document => document.name.toLowerCase().includes(search.trim().toLowerCase())), [documents, search, selectedCollectionId])
  const visibleDocumentIds = useMemo(() => filtered.map(document => document.id), [filtered])
  const visibleDocumentIdSet = useMemo(() => new Set(visibleDocumentIds), [visibleDocumentIds])
  const selectedVisibleCount = selectedDocumentIds.filter(id => visibleDocumentIdSet.has(id)).length
  const activeProject = projects.find(project => project.id === selectedProjectId)
  const activeFolder = folders.find(folder => folder.id === selectedFolderId)
  const allVisibleSelected = filtered.length > 0 && selectedVisibleCount === filtered.length
  const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected

  useEffect(() => {
    if (headerSelectAllRef.current) headerSelectAllRef.current.indeterminate = someVisibleSelected
    if (toolbarSelectAllRef.current) toolbarSelectAllRef.current.indeterminate = someVisibleSelected
  }, [someVisibleSelected])

  useEffect(() => {
    setSelectedDocumentIds(previous => previous.filter(id => visibleDocumentIdSet.has(id)))
  }, [visibleDocumentIdSet])

  const requestDelete = (document: PolicyDocument, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    deleteTriggerRef.current = event.currentTarget
    setDeleteError('')
    setBulkDeleteOpen(false)
    setDocumentToDelete(document)
  }

  const saveNewFolder = async () => {
    const name = newFolderName.trim()
    if (!name) {
      showToast('Folder name is required.')
      return
    }
    try {
      await createFolder(name)
      setNewFolderName('')
      setCreatingFolder(false)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to create folder.')
    }
  }

  const startRenameFolder = (folderId: string, name: string) => {
    setEditingFolderId(folderId)
    setEditingFolderName(name)
  }

  const requestDeleteFolder = (folderId: string, name: string, event?: MouseEvent<HTMLButtonElement>) => {
    if (event) event.stopPropagation()
    setFolderToDelete({ id: folderId, name })
  }

  const confirmDeleteFolder = async () => {
    if (!folderToDelete) return
    setIsDeletingFolder(true)
    try {
      await deleteFolder(folderToDelete.id)
      setFolderToDelete(null)
      showToast(`Folder "${folderToDelete.name}" deleted.`)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to delete folder.')
    } finally {
      setIsDeletingFolder(false)
    }
  }

  const saveFolderRename = async () => {
    const name = editingFolderName.trim()
    if (!editingFolderId || !name) {
      showToast('Folder name is required.')
      return
    }
    try {
      await renameFolder(editingFolderId, name)
      setEditingFolderId(null)
      setEditingFolderName('')
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to rename folder.')
    }
  }

  const archiveFolder = async (folderId: string, name: string) => {
    if (!window.confirm(`Archive "${name}"? Documents will remain in the project.`)) return
    try {
      await deleteFolder(folderId)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to archive folder.')
    }
  }

  const toggleDocumentSelection = (documentId: string, checked: boolean) => {
    setSelectedDocumentIds(previous => {
      if (checked) return previous.includes(documentId) ? previous : [...previous, documentId]
      return previous.filter(id => id !== documentId)
    })
  }

  const toggleAllVisibleDocuments = (checked: boolean) => {
    setSelectedDocumentIds(checked ? visibleDocumentIds : [])
  }

  const requestBulkDelete = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    if (selectedVisibleCount === 0) return
    deleteTriggerRef.current = event.currentTarget
    setDeleteError('')
    setDocumentToDelete(null)
    setBulkDeleteOpen(true)
  }

  const cancelDelete = () => {
    if (isDeleting) return
    setDocumentToDelete(null)
    setBulkDeleteOpen(false)
    setDeleteError('')
    window.setTimeout(() => deleteTriggerRef.current?.focus(), 0)
  }

  const confirmDelete = async () => {
    if (isDeleting) return
    setIsDeleting(true)
    setDeleteError('')
    try {
      if (bulkDeleteOpen) {
        const targets = selectedDocumentIds.filter(id => visibleDocumentIdSet.has(id))
        const failedIds: string[] = []
        for (const id of targets) {
          try {
            await removeDocument(id)
          } catch {
            failedIds.push(id)
          }
        }
        setSelectedDocumentIds(failedIds)
        if (failedIds.length > 0) {
          const deletedCount = targets.length - failedIds.length
          setDeleteError(deletedCount > 0 ? `${deletedCount} deleted. ${failedIds.length} could not be deleted.` : 'Unable to delete the selected documents. Please try again.')
          return
        }
        setBulkDeleteOpen(false)
      } else if (documentToDelete) {
        await removeDocument(documentToDelete.id)
        setDocumentToDelete(null)
      }
    } catch (error) {
      setDeleteError(error instanceof Error && error.message ? error.message : 'Unable to delete the document. Please try again.')
    } finally {
      setIsDeleting(false)
    }
  }

  return <section className="min-w-0 flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 sm:px-7 sm:py-7">
    <div className="mx-auto max-w-[1000px]">
      <div className="mb-2 flex items-center gap-3">
        <button type="button" onClick={() => setSidebarOpen(true)} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-slate-500 shadow-sm hover:bg-blue-50 hover:text-blue-600 lg:hidden" aria-label="Open sidebar"><Menu size={20} /></button>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-[-.035em] text-slate-900 sm:text-[28px]">{activeProject ? activeProject.name : 'Documents'}</h1>
          {activeProject && <p className="mt-1 text-[12px] text-slate-600">Manage files and folders for this project.</p>}
        </div>
        <div className="ml-auto hidden items-center gap-2 sm:flex">
          <div className="relative">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input id="library-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search documents" className="h-10 w-64 rounded-xl border border-[#e6ecf5] bg-white pl-9 pr-3 text-[12px] outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100/60" />
          </div>
          <button type="button" onClick={onUpload} className="flex h-10 shrink-0 items-center gap-2 rounded-xl bg-blue-600 px-4 text-[12px] font-semibold text-white shadow-[0_5px_16px_rgba(37,99,235,.22)] hover:bg-blue-700"><Upload size={16} />Upload</button>
        </div>
      </div>

      {!activeProject && (projects.length > 0 || collections.length > 0) && <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        <button type="button" onClick={() => navigate('/documents')} className={`flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold ${selectedProjectId === null && selectedCollectionId === null ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`}><FolderOpen size={15} />All documents</button>
        {projects.map(project => <button key={project.id} type="button" onClick={() => navigate(`/projects/${encodeURIComponent(project.id)}`)} className={`flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold ${selectedProjectId === project.id && selectedFolderId === null ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`}><FolderOpen size={15} />{project.name}</button>)}
        {collections.map(collection => <button key={collection.id} type="button" onClick={() => setSelectedCollectionId(collection.id)} className={`flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold ${selectedCollectionId === collection.id ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`}><FolderOpen size={15} />{collection.name}<span className="text-[10px] text-slate-400">{collection.document_count ?? 0}</span></button>)}
      </div>}

      {activeProject && <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-[13px] font-semibold text-slate-900">Folders</h2>
            <span className="inline-flex h-6 items-center rounded-full bg-slate-100 px-2 text-[10px] font-medium text-slate-600">{folders.length}</span>
          </div>
          <button type="button" onClick={() => setCreatingFolder(true)} className="flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 hover:border-blue-200 hover:text-blue-600"><Plus size={14} />New Folder</button>
        </div>
        {folders.length > 0 ? <div>
          <div className="hidden grid-cols-[minmax(0,1fr)_110px_120px_44px] gap-4 border-b border-slate-200 px-3 py-2 text-[10px] font-semibold uppercase tracking-[.08em] text-slate-400 sm:grid">
            <span>Name</span><span>Documents</span><span>Modified</span><span />
          </div>
          <div className="space-y-1">
            {folders.map(folder => <div key={folder.id} className={`group relative grid grid-cols-[minmax(0,1fr)_44px] items-center gap-2 rounded-lg border px-3 py-2.5 text-[12px] sm:grid-cols-[minmax(0,1fr)_110px_120px_44px] sm:gap-4 ${selectedFolderId === folder.id ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              {editingFolderId === folder.id ? <input value={editingFolderName} onChange={event => setEditingFolderName(event.target.value)} className="field h-8 min-w-0" autoFocus /> : <button type="button" onClick={() => navigate(`/projects/${encodeURIComponent(activeProject.id)}/folders/${encodeURIComponent(folder.id)}`)} className="flex min-w-0 items-center gap-2 text-left font-semibold text-slate-900 hover:text-blue-600">
                <FolderOpen size={15} className="shrink-0 text-slate-400" />
                <span className="truncate">{folder.name}</span>
              </button>}
              <span className="hidden text-slate-600 sm:block">{folder.document_count} document{folder.document_count !== 1 ? 's' : ''}</span>
              <span className="hidden text-slate-500 sm:block">{relativeDate(folder.updated_at)}</span>
              <div className="relative flex justify-end">
                {editingFolderId === folder.id ? (
                  <>
                    <button type="button" onClick={() => void saveFolderRename()} className="grid h-7 w-7 place-items-center rounded-lg text-slate-500 hover:bg-blue-100 hover:text-blue-600" aria-label={`Save ${folder.name}`}><Check size={14} /></button>
                    <button type="button" onClick={() => setEditingFolderId(null)} className="grid h-7 w-7 place-items-center rounded-lg text-slate-500 hover:bg-slate-100" aria-label="Cancel rename"><X size={14} /></button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={(event) => { event.stopPropagation(); setFolderMenuId(folderMenuId === folder.id ? null : folder.id) }} className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label={`Menu for ${folder.name}`}>⋮</button>
                    {folderMenuId === folder.id && (
                      <div className="absolute right-0 top-8 z-20 w-40 rounded-lg border border-slate-200 bg-white shadow-lg" onClick={(e) => e.stopPropagation()}>
                        <button type="button" onClick={() => { setFolderMenuId(null); startRenameFolder(folder.id, folder.name) }} className="block w-full px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50">Edit</button>
                        <button type="button" onClick={() => { setFolderMenuId(null); requestDeleteFolder(folder.id, folder.name, { stopPropagation: () => {} } as any) }} className="block w-full px-3 py-2 text-left text-[12px] text-red-600 hover:bg-red-50">Delete</button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>)}
          </div>
        </div> : <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/50 px-4 py-8 text-center text-[12px] text-slate-500">No folders yet. Create one to organize your documents.</div>}
      </section>}

      <div className="mb-4 flex gap-2 sm:hidden">
        <div className="relative min-w-0 flex-1"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input id="library-search-mobile" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search documents" className="h-10 w-full rounded-xl border border-[#e6ecf5] bg-white pl-9 pr-3 text-[12px] outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100/60" /></div>
        <button type="button" onClick={onUpload} className="flex h-10 shrink-0 items-center gap-2 rounded-xl bg-blue-600 px-4 text-[12px] font-semibold text-white shadow-[0_5px_16px_rgba(37,99,235,.22)] hover:bg-blue-700"><Upload size={16} />Upload</button>
      </div>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-[13px] font-semibold text-slate-900">Documents</h2>
            <span className="inline-flex h-6 items-center rounded-full bg-slate-100 px-2 text-[10px] font-medium text-slate-600">{filtered.length}</span>
          </div>
          {filtered.length > 0 && <div className="hidden items-center gap-3 sm:flex">
            <div className="flex items-center gap-2 text-[11px] text-slate-600">
              <span>Sort by: Modified (Newest)</span>
              <ChevronDown size={14} />
            </div>
            <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
              <button type="button" className="grid h-6 w-6 place-items-center rounded text-slate-600 hover:bg-slate-100" aria-label="List view">⊞</button>
            </div>
          </div>}
        </div>

        {selectedVisibleCount > 0 && <div className="mb-3 flex min-h-10 items-center gap-3 rounded-lg border border-blue-100 bg-blue-50/70 px-3 text-[12px] font-semibold text-slate-700">
          <input ref={toolbarSelectAllRef} type="checkbox" checked={allVisibleSelected} onChange={event => toggleAllVisibleDocuments(event.currentTarget.checked)} className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" aria-label="Select all documents" />
          <span className="min-w-0 flex-1">{selectedVisibleCount} selected</span>
          <button type="button" disabled={isDeleting} onClick={requestBulkDelete} className="grid h-7 w-7 place-items-center rounded-lg text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50" aria-label="Delete selected documents"><Trash2 size={14} /></button>
        </div>}

        <div className="hidden grid-cols-[28px_minmax(0,1fr)_130px_90px_44px] gap-4 border-b border-slate-200 px-3 py-2 text-[10px] font-semibold uppercase tracking-[.08em] text-slate-400 sm:grid">
          <input ref={headerSelectAllRef} type="checkbox" checked={allVisibleSelected} disabled={!filtered.length} onChange={event => toggleAllVisibleDocuments(event.currentTarget.checked)} className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40" aria-label="Select all documents" />
          <span>Name</span><span>Modified</span><span>Size</span><span />
        </div>
        <div className="space-y-1">
          {filtered.map(document => {
            const isSelected = selectedDocumentIds.includes(document.id)
            return <article key={document.id} className={`relative grid grid-cols-[28px_minmax(0,1fr)_44px] items-center gap-2 rounded-lg border px-3 py-2.5 text-[12px] sm:grid-cols-[28px_minmax(0,1fr)_130px_90px_44px] sm:gap-4 ${isSelected ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              <input type="checkbox" checked={isSelected} onChange={event => toggleDocumentSelection(document.id, event.currentTarget.checked)} onClick={event => event.stopPropagation()} className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" aria-label={`Select document ${document.name}`} />
              <button type="button" onClick={() => setSelectedDocument(document)} className="flex min-w-0 items-center gap-2.5 text-left">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-600"><FileText size={15} /></span>
                <span className="min-w-0"><span className="block truncate font-semibold text-slate-900 hover:text-blue-600">{document.name}</span><span className="block text-[10px] text-slate-400 sm:hidden">{relativeDate(document.updatedAt)} · {document.size}</span></span>
              </button>
              <span className="hidden text-slate-600 sm:block">{relativeDate(document.updatedAt)}</span>
              <span className="hidden text-slate-600 sm:block">{document.size}</span>
              <button type="button" disabled={isDeleting && documentToDelete?.id === document.id} onClick={event => requestDelete(document, event)} className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50" aria-label={`Delete ${document.name}`}><Trash2 size={14} /></button>
            </article>
          })}
          {filtered.length > 0 && <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-slate-50/50 px-4 py-10 text-center">
            <div className="flex justify-center text-slate-300 mb-3"><svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg></div>
            <p className="text-[13px] text-slate-600 font-medium">Drag and drop files here to upload</p>
            <p className="text-[12px] text-slate-500 mt-1">or</p>
            <button type="button" onClick={onUpload} className="mt-3 inline-flex h-8 items-center gap-2 rounded-lg bg-blue-600 px-3 text-[12px] font-semibold text-white hover:bg-blue-700">Upload files</button>
          </div>}
          {!filtered.length && <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/50 px-4 py-12 text-center text-[13px] text-slate-600">
            <FileText className="mx-auto text-slate-300" size={28} />
            <p className="mt-3 font-medium">{activeFolder ? 'No documents in this folder yet' : 'No documents found.'}</p>
            {activeFolder && <button type="button" onClick={onUpload} className="mt-4 inline-flex h-8 items-center gap-2 rounded-lg bg-blue-600 px-3 text-[12px] font-semibold text-white hover:bg-blue-700"><Upload size={14} />Upload documents</button>}
          </div>}
        </div>
      </section>
      {folderToDelete && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4">
        <div className="w-full max-w-[360px] rounded-xl border border-slate-200 bg-white p-5 shadow-lg sm:p-6">
          <h2 className="text-lg font-semibold text-slate-900">Delete folder?</h2>
          <p className="mt-2 text-sm text-slate-600">This action cannot be undone.</p>
          <div className="mt-6 flex justify-end gap-2">
            <button type="button" onClick={() => setFolderToDelete(null)} disabled={isDeletingFolder} className="px-4 py-2 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed">Cancel</button>
            <button type="button" onClick={() => void confirmDeleteFolder()} disabled={isDeletingFolder} className="px-4 py-2 rounded-lg bg-red-600 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed">Delete</button>
          </div>
        </div>
      </div>}
      <Modal open={creatingFolder} onClose={() => { setCreatingFolder(false); setNewFolderName('') }} title="Create new folder">
        <form onSubmit={event => { event.preventDefault(); void saveNewFolder() }}>
          <input value={newFolderName} onChange={event => setNewFolderName(event.target.value)} className="field h-10 w-full" placeholder="Folder name" autoFocus />
          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => { setCreatingFolder(false); setNewFolderName('') }}>Cancel</Button>
            <Button type="submit" size="sm" disabled={!newFolderName.trim()}>Create</Button>
          </div>
        </form>
      </Modal>
    </div>
    <DocumentDeleteModal open={documentToDelete !== null || bulkDeleteOpen} documentName={documentToDelete?.name ?? ''} documentCount={bulkDeleteOpen ? selectedVisibleCount : undefined} isDeleting={isDeleting} error={deleteError} onCancel={cancelDelete} onConfirm={() => void confirmDelete()} />
  </section>
}
