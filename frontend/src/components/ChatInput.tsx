import { ArrowUp, Plus } from 'lucide-react'
import { useLayoutEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { useApp } from '../context/AppContext'

type FormValues = { question: string }

const MAX_TEXTAREA_HEIGHT = 150

function resizeTextarea(textarea: HTMLTextAreaElement | null) {
  if (!textarea) return

  textarea.style.height = 'auto'
  const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)
  textarea.style.height = `${nextHeight}px`
  textarea.style.overflowY = textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden'
}

export default function ChatInput({ onUpload }: { onUpload: () => void }) {
  const { sendMessage, loading, projects, folders, collections, selectedProjectId, setSelectedProjectId, selectedFolderId, setSelectedFolderId, selectedCollectionId, setSelectedCollectionId, selectedDocument, setSelectedDocument } = useApp()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const { register, handleSubmit, reset, watch } = useForm<FormValues>({ defaultValues: { question: '' } })
  const question = watch('question')
  const field = register('question')
  const canSend = Boolean(question.trim()) && !loading
  const sourceValue = selectedDocument?.uploaded
    ? `document:${selectedDocument.id}`
    : selectedCollectionId !== null
      ? `collection:${selectedCollectionId}`
      : selectedFolderId
        ? `folder:${selectedFolderId}`
        : selectedProjectId
        ? `project:${selectedProjectId}`
        : 'all'

  const chooseSource = (value: string) => {
    setSelectedDocument(null)
    setSelectedCollectionId(null)
    setSelectedProjectId(null)
    setSelectedFolderId(null)
    if (value.startsWith('project:')) setSelectedProjectId(value.slice('project:'.length))
    if (value.startsWith('folder:')) {
      const folderId = value.slice('folder:'.length)
      const folder = folders.find(item => item.id === folderId)
      if (folder) {
        setSelectedProjectId(folder.project_id)
        setSelectedFolderId(folder.id)
      }
    }
    if (value.startsWith('collection:')) setSelectedCollectionId(Number(value.slice('collection:'.length)))
  }

  useLayoutEffect(() => {
    resizeTextarea(textareaRef.current)
  }, [question])

  const submit = ({ question: value }: FormValues) => {
    if (!value.trim() || loading) return
    void sendMessage(value.trim())
    reset()
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.overflowY = 'hidden'
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} className="w-full">
      <div className="mx-auto w-full max-w-[812px] px-2 sm:px-4">
        <div className="chat-composer">
          <div className="chat-composer__input-area">
            <textarea
              {...field}
              ref={element => {
                field.ref(element)
                textareaRef.current = element
              }}
              rows={1}
              className="chat-composer__textarea"
              placeholder="Ask anything about your uploaded documents..."
              aria-label="Message input"
              onInput={event => resizeTextarea(event.currentTarget)}
              onKeyDown={event => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  if (canSend) void handleSubmit(submit)()
                }
              }}
            />
          </div>

          <div className="chat-composer__actions">
            <div className="chat-composer__actions-left">
              <button type="button" onClick={onUpload} className="chat-composer__icon-button" aria-label="Attach document">
                <Plus size={20} />
              </button>
              <select value={sourceValue} onChange={event => chooseSource(event.target.value)} className="h-8 max-w-[180px] rounded-lg border border-transparent bg-transparent px-2 text-xs font-semibold text-slate-600 outline-none hover:bg-slate-50 focus:border-blue-200 focus:bg-white focus:ring-2 focus:ring-blue-100" aria-label="Answer source">
                <option value="all">All documents</option>
                {projects.map(project => <option key={project.id} value={`project:${project.id}`}>Project: {project.name}</option>)}
                {folders.map(folder => <option key={folder.id} value={`folder:${folder.id}`}>Folder: {folder.name}</option>)}
                {collections.map(collection => <option key={collection.id} value={`collection:${collection.id}`}>Folder: {collection.name}</option>)}
                {selectedDocument?.uploaded && <option value={`document:${selectedDocument.id}`}>Document: {selectedDocument.name}</option>}
              </select>
            </div>

            <div className="chat-composer__actions-right">
              <button type="submit" disabled={!canSend} className="chat-composer__send-button" aria-label={loading ? 'Sending message' : 'Send message'}>
                <ArrowUp size={18} strokeWidth={2.3} />
              </button>
            </div>
          </div>
        </div>

        <p className="py-2 text-center text-[10px] text-slate-400">Answers are generated from retrieved document context.</p>
      </div>
    </form>
  )
}
