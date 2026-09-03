import { AlertCircle, CheckCircle2, Clock3, Download, FileText, Highlighter, RotateCcw, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { fetchDocumentFile, listDocumentVersions, makeDocumentVersionCurrent, uploadDocumentVersion, type DocumentVersion } from '../services/api'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

const BROWSER_PREVIEW_TYPES = new Set(['PDF', 'PNG', 'JPG', 'JPEG', 'BMP', 'GIF', 'WEBP', 'TXT', 'CSV'])

// Limit embedded previews to formats browsers can render from a blob URL.
function canBrowserPreview(type: string) {
  return BROWSER_PREVIEW_TYPES.has(type)
}

export default function DocumentPreviewModal() {
  const { selectedDocument, setSelectedDocument, retrievedDocuments, refreshDocuments, showToast } = useApp()
  const [versions, setVersions] = useState<DocumentVersion[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [versionError, setVersionError] = useState('')
  const [uploadingVersion, setUploadingVersion] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [previewError, setPreviewError] = useState('')

  useEffect(() => {
    if (!selectedDocument?.uploaded) return
    let active = true
    setLoadingVersions(true)
    setVersionError('')
    void listDocumentVersions(selectedDocument.id)
      .then(result => { if (active) setVersions(result.versions) })
      .catch(error => { if (active) setVersionError(error instanceof Error ? error.message : 'Unable to load version history.') })
      .finally(() => { if (active) setLoadingVersions(false) })
    return () => { active = false }
  }, [selectedDocument?.id, selectedDocument?.uploaded])

  useEffect(() => {
    if (!selectedDocument?.uploaded || !canBrowserPreview(selectedDocument.type)) {
      setPreviewUrl('')
      setPreviewError('')
      setLoadingPreview(false)
      return
    }
    let active = true
    let objectUrl = ''
    setPreviewUrl('')
    setLoadingPreview(true)
    setPreviewError('')
    void fetchDocumentFile(selectedDocument.id)
      .then(blob => {
        objectUrl = URL.createObjectURL(blob)
        if (active) setPreviewUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch(error => { if (active) setPreviewError(error instanceof Error ? error.message : 'Unable to load document preview.') })
      .finally(() => { if (active) setLoadingPreview(false) })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [selectedDocument?.id, selectedDocument?.type, selectedDocument?.uploaded])

  if (!selectedDocument) return null
  const reference = retrievedDocuments.find(source => source.id === selectedDocument.id || source.name === selectedDocument.name)
  const previewable = selectedDocument.uploaded && canBrowserPreview(selectedDocument.type)

  const makeCurrent = async (version: DocumentVersion) => {
    await makeDocumentVersionCurrent(selectedDocument.id, version.id)
    setVersions(previous => previous.map(item => ({ ...item, is_current: item.id === version.id })))
    await refreshDocuments()
    showToast(`Version ${version.version_number} is now current`)
  }

  const addVersion = async (file: File) => {
    setUploadingVersion(true)
    setVersionError('')
    try {
      await uploadDocumentVersion(selectedDocument.id, file)
      const result = await listDocumentVersions(selectedDocument.id)
      setVersions(result.versions)
      await refreshDocuments()
      showToast('New document version processed')
    } catch (error) {
      setVersionError(error instanceof Error ? error.message : 'Version upload failed.')
    } finally {
      setUploadingVersion(false)
    }
  }

  // Fetch through the authenticated file endpoint so private documents never need a public URL.
  const downloadSelectedDocument = async () => {
    try {
      const blob = await fetchDocumentFile(selectedDocument.id, true)
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = selectedDocument.name
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to download document.')
    }
  }

  return (
    <Modal open onClose={() => setSelectedDocument(null)} title={selectedDocument.name}>
      <div className="flex items-center justify-between rounded-2xl border border-[#eef2f7] bg-[#f8fbff] p-3 shadow-[0_4px_16px_rgba(37,99,235,.04)]">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-500 text-white shadow-[0_5px_14px_rgba(37,99,235,.18)]"><FileText size={19} /></span>
          <div>
            <p className="text-xs font-semibold">{selectedDocument.type} · {selectedDocument.size}</p>
            <p className="text-[10px] text-slate-500">Current version {selectedDocument.currentVersionNumber ?? '—'} · {selectedDocument.visibility ?? 'private'}</p>
          </div>
        </div>
        {selectedDocument.uploaded && <Button type="button" variant="secondary" size="sm" onClick={() => void downloadSelectedDocument()}><Download size={14} />Download</Button>}
      </div>
      <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {previewable && loadingPreview && <div className="grid min-h-[320px] place-items-center text-xs font-semibold text-slate-500">Loading preview...</div>}
        {previewable && previewError && <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 p-5 text-center">
          <AlertCircle size={20} className="text-amber-600" />
          <p className="text-sm font-semibold text-slate-900">Preview is unavailable</p>
          <p className="max-w-sm text-xs text-slate-500">{previewError}</p>
          <Button type="button" variant="secondary" size="sm" onClick={() => void downloadSelectedDocument()}><Download size={14} />Download</Button>
        </div>}
        {previewable && previewUrl && !loadingPreview && !previewError && (
          selectedDocument.type === 'PDF'
            ? <iframe title={`Preview ${selectedDocument.name}`} src={previewUrl} className="h-[60vh] min-h-[360px] w-full bg-white" />
            : ['TXT', 'CSV'].includes(selectedDocument.type)
              ? <iframe title={`Preview ${selectedDocument.name}`} src={previewUrl} className="h-[50vh] min-h-[320px] w-full bg-white" />
              : <div className="grid max-h-[60vh] min-h-[260px] place-items-center overflow-auto bg-slate-50 p-3"><img src={previewUrl} alt={selectedDocument.name} className="max-h-[56vh] max-w-full object-contain" /></div>
        )}
        {!previewable && <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 p-5 text-center">
          <FileText size={24} className="text-slate-400" />
          <p className="text-sm font-semibold text-slate-900">Preview is not available for this file type</p>
          <p className="max-w-sm text-xs text-slate-500">{selectedDocument.name} can still be downloaded as the original uploaded file.</p>
          {selectedDocument.uploaded && <Button type="button" variant="secondary" size="sm" onClick={() => void downloadSelectedDocument()}><Download size={14} />Download</Button>}
        </div>}
      </div>
      {reference && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-yellow-200 bg-yellow-50 p-3 text-[11px] font-semibold text-yellow-800">
          <Highlighter size={14} /> Selected by semantic retrieval. Ranking signals are not factual confidence.
        </div>
      )}
      <div className="mt-4">
        <div className="flex items-center justify-between"><p className="text-xs font-semibold text-slate-700">Version history</p><label className="cursor-pointer rounded-lg bg-blue-50 px-3 py-1.5 text-[10px] font-semibold text-blue-700 hover:bg-blue-100">{uploadingVersion ? 'Processing…' : 'Upload new version'}<input type="file" className="hidden" disabled={uploadingVersion} onChange={event => { const file = event.target.files?.[0]; if (file) void addVersion(file); event.currentTarget.value = '' }} /></label></div>
        {loadingVersions && <p className="mt-2 text-xs text-slate-400">Loading versions…</p>}
        {versionError && <p className="mt-2 text-xs text-red-600">{versionError}</p>}
        <div className="mt-2 space-y-2">
          {versions.map(version => (
            <div key={version.id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-xs">
              {version.status === 'completed' ? <CheckCircle2 size={15} className="text-emerald-600" /> : version.status === 'failed' ? <XCircle size={15} className="text-red-600" /> : <Clock3 size={15} className="text-blue-600" />}
              <div className="min-w-0 flex-1">
                <p className="font-semibold">Version {version.version_number}{version.is_current ? ' · Current' : ''}</p>
                <p className="truncate text-[10px] text-slate-500">{version.error?.message ?? version.status}</p>
              </div>
              {!version.is_current && version.status === 'completed' && <Button variant="secondary" onClick={() => void makeCurrent(version)}><RotateCcw size={13} />Use</Button>}
            </div>
          ))}
        </div>
      </div>
    </Modal>
  )
}
