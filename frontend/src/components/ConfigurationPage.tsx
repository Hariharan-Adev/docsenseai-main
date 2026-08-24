import { Building2, ChevronLeft, ChevronRight, Cloud, CloudCog, Eye, EyeOff, Github, Plus, Search } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useApp } from '../context/AppContext'
import { ApiError, testAzureDevOpsConnection, type AzureDevOpsProject } from '../services/api'
import { Button } from './ui/Button'
import { Card } from './ui/Card'

const integrationCatalog = [
  { id: 'azure-dev', name: 'Azure Dev', description: 'Connect projects, work items, and development data.', icon: CloudCog },
  { id: 'github', name: 'GitHub', description: 'Connect repositories and development workflows.', icon: Github },
  { id: 'sharepoint', name: 'SharePoint', description: 'Connect team sites and shared document libraries.', icon: Building2 },
  { id: 'google-drive', name: 'Google Drive', description: 'Connect files and folders from Google Drive.', icon: Cloud },
] as const

type GitHubConfiguration = {
  organization: string
  personalAccessToken: string
  connected: boolean
  repository: string
  branch: string
  contentTypes: string[]
  includePaths: string
  excludePaths: string
  fileTypes: string[]
  titleMapping: string
  contentMapping: string
  metadataFields: string[]
  syncMode: 'manual' | 'scheduled'
  frequency: string
  incrementalSync: boolean
}

const initialGitHubConfiguration: GitHubConfiguration = {
  organization: '',
  personalAccessToken: '',
  connected: false,
  repository: 'docsense-ai',
  branch: 'main',
  contentTypes: ['source_files', 'readme_markdown', 'documentation'],
  includePaths: 'src/**, docs/**, README.md',
  excludePaths: 'node_modules/**, dist/**, .git/**',
  fileTypes: ['.md', '.txt', '.ts', '.tsx', '.js', '.py'],
  titleMapping: 'file_name_path',
  contentMapping: 'file_content',
  metadataFields: ['repository', 'branch', 'path', 'commit_sha'],
  syncMode: 'scheduled',
  frequency: '1h',
  incrementalSync: true,
}

type ConfigurationPageProps = {
  onBack: () => void
  onNavigate: (integrationId: string | null) => void
  routeIntegrationId?: string
}

// Renders integration configuration while keeping its selection synchronized with the URL.
export default function ConfigurationPage({ onBack, onNavigate, routeIntegrationId }: ConfigurationPageProps) {
  const { showToast } = useApp()
  const [selectedIntegration, setSelectedIntegration] = useState<'azure-dev' | 'catalog' | 'github' | null>(null)
  const [integrationSearch, setIntegrationSearch] = useState('')
  const [organizationUrl, setOrganizationUrl] = useState('')
  const [personalAccessToken, setPersonalAccessToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [selectedProject, setSelectedProject] = useState('')
  const [workItemTypes, setWorkItemTypes] = useState(['Bug', 'User Story'])
  const [states, setStates] = useState(['New', 'Active'])
  const [titleField, setTitleField] = useState('System.Title')
  const [contentField, setContentField] = useState('System.Description')
  const [metadataFields, setMetadataFields] = useState(['System.State', 'System.WorkItemType', 'System.Tags', 'System.AreaPath'])
  const [syncMode, setSyncMode] = useState<'manual' | 'scheduled'>('scheduled')
  const [frequency, setFrequency] = useState('Every 1 hour')
  const [syncChangedOnly, setSyncChangedOnly] = useState(true)
  const [savedGitHubConfiguration, setSavedGitHubConfiguration] = useState<GitHubConfiguration | null>(null)
  const [githubDraft, setGitHubDraft] = useState<GitHubConfiguration>({ ...initialGitHubConfiguration })
  const [showGitHubToken, setShowGitHubToken] = useState(false)
  const [testingGitHubConnection, setTestingGitHubConnection] = useState(false)
  const [savingGitHubConfiguration, setSavingGitHubConfiguration] = useState(false)
  const [testingAzureDevConnection, setTestingAzureDevConnection] = useState(false)
  const [azureDevConnected, setAzureDevConnected] = useState(false)
  const [azureDevProjects, setAzureDevProjects] = useState<AzureDevOpsProject[]>([])
  const [azureDevConnectionMessage, setAzureDevConnectionMessage] = useState('Use Test Connection to verify the current credentials.')
  const [azureDevDeleted, setAzureDevDeleted] = useState(false)
  const [integrationMenuId, setIntegrationMenuId] = useState<'azure-dev' | 'github' | null>(null)
  const [pendingConfirmation, setPendingConfirmation] = useState<{ integrationId: 'azure-dev' | 'github'; action: 'disconnect' | 'reconnect' | 'delete' } | null>(null)
  const integrationMenuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const routeSelection = routeIntegrationId === 'azure-dev' || routeIntegrationId === 'github' || routeIntegrationId === 'catalog' ? routeIntegrationId : null
    setSelectedIntegration(routeSelection)
  }, [routeIntegrationId])

  useEffect(() => {
    if (!integrationMenuId) return

    // Close an open 3-dot menu from outside clicks while preserving menu item clicks.
    const closeMenuFromOutsideClick = (event: PointerEvent) => {
      const target = event.target
      if (target instanceof Node && !integrationMenuRef.current?.contains(target)) {
        setIntegrationMenuId(null)
      }
    }

    document.addEventListener('pointerdown', closeMenuFromOutsideClick)
    return () => document.removeEventListener('pointerdown', closeMenuFromOutsideClick)
  }, [integrationMenuId])

  // Updates both local rendering state and browser history for user-driven selections.
  const selectIntegration = (integrationId: 'azure-dev' | 'catalog' | 'github' | null) => {
    setSelectedIntegration(integrationId)
    onNavigate(integrationId)
  }

  const visibleIntegrations = integrationCatalog.filter(integration => integration.name.toLowerCase().includes(integrationSearch.trim().toLowerCase()))

  // Credential edits invalidate the previous live Azure DevOps verification.
  const updateAzureCredentials = (field: 'organizationUrl' | 'personalAccessToken', value: string) => {
    if (field === 'organizationUrl') setOrganizationUrl(value)
    else setPersonalAccessToken(value)
    setAzureDevConnected(false)
    setAzureDevProjects([])
    setSelectedProject('')
    setAzureDevConnectionMessage('Use Test Connection to verify the current credentials.')
  }

  // Updates a checkbox group without duplicating values.
  const toggleOption = (value: string, selected: string[], update: (values: string[]) => void) => {
    update(selected.includes(value) ? selected.filter(option => option !== value) : [...selected, value])
  }

  // Restores the unsaved Azure configuration form to its initial values.
  const cancelAzureChanges = () => {
    setOrganizationUrl('')
    setPersonalAccessToken('')
    setShowToken(false)
    setSelectedProject('')
    setAzureDevConnected(false)
    setAzureDevProjects([])
    setAzureDevConnectionMessage('Use Test Connection to verify the current credentials.')
    setWorkItemTypes(['Bug', 'User Story'])
    setStates(['New', 'Active'])
    setTitleField('System.Title')
    setContentField('System.Description')
    setMetadataFields(['System.State', 'System.WorkItemType', 'System.Tags', 'System.AreaPath'])
    setSyncMode('scheduled')
    setFrequency('Every 1 hour')
    setSyncChangedOnly(true)
  }

  const fieldOptions = ['System.Title', 'System.Description', 'System.State', 'System.WorkItemType', 'System.Tags', 'System.AreaPath']
  const organizationSummary = organizationUrl.trim() || 'Not set'

  // Calls the backend so Connected means Azure DevOps returned projects for this PAT.
  const handleTestAzureConnection = async () => {
    if (testingAzureDevConnection) return
    if (!organizationUrl.trim() || !personalAccessToken.trim()) {
      showToast('Enter an Azure DevOps organization URL and personal access token')
      return
    }
    setTestingAzureDevConnection(true)
    setAzureDevConnected(false)
    setAzureDevProjects([])
    setSelectedProject('')
    try {
      const result = await testAzureDevOpsConnection(organizationUrl, personalAccessToken)
      setOrganizationUrl(result.organization_url)
      setAzureDevProjects(result.projects)
      setSelectedProject(result.projects[0]?.id ?? '')
      setAzureDevConnected(result.connected && result.projects.length > 0)
      setAzureDevConnectionMessage(`Verified ${result.projects.length} Azure DevOps project${result.projects.length === 1 ? '' : 's'}.`)
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Azure DevOps connection test failed.'
      setAzureDevConnectionMessage(message)
      showToast(message)
    } finally {
      setTestingAzureDevConnection(false)
    }
  }
  // Opens GitHub with a fresh copy so Cancel can discard edits without changing the saved configuration.
  const openGitHubConfiguration = () => {
    setGitHubDraft({ ...(savedGitHubConfiguration ?? initialGitHubConfiguration) })
    setShowGitHubToken(false)
    selectIntegration('github')
  }

  // Keeps connection status tied to the exact credentials that were tested.
  const updateGitHubCredentials = (field: 'organization' | 'personalAccessToken', value: string) => {
    setGitHubDraft(current => ({ ...current, [field]: value, connected: false }))
  }

  // Simulates the future GitHub credential verification without making a network request.
  const handleTestGitHubConnection = async () => {
    if (testingGitHubConnection) return
    if (!githubDraft.organization.trim() || !githubDraft.personalAccessToken.trim()) {
      showToast('Enter a GitHub account or organization and personal access token')
      return
    }
    const testedOrganization = githubDraft.organization
    const testedToken = githubDraft.personalAccessToken
    setTestingGitHubConnection(true)
    await new Promise(resolve => setTimeout(resolve, 400))
    setGitHubDraft(current => ({
      ...current,
      connected: current.organization === testedOrganization && current.personalAccessToken === testedToken,
    }))
    setTestingGitHubConnection(false)
  }

  // Validates and stores one local GitHub configuration until backend persistence is available.
  const handleSaveGitHubConfiguration = async () => {
    if (savingGitHubConfiguration) return
    const missingRequiredValue = !githubDraft.organization.trim()
      || !githubDraft.personalAccessToken.trim()
      || !githubDraft.connected
      || !githubDraft.repository
      || !githubDraft.branch
      || !githubDraft.contentTypes.length
      || !githubDraft.fileTypes.length
      || !githubDraft.titleMapping
      || !githubDraft.contentMapping
      || !githubDraft.syncMode
      || (githubDraft.syncMode === 'scheduled' && !githubDraft.frequency)
    if (missingRequiredValue) {
      showToast('Complete all required GitHub fields and test the connection before saving')
      return
    }
    setSavingGitHubConfiguration(true)
    await new Promise(resolve => setTimeout(resolve, 250))
    setSavedGitHubConfiguration({ ...githubDraft })
    setSavingGitHubConfiguration(false)
    showToast('GitHub configuration saved')
  }

  const handleIntegrationRowOpen = (id: 'azure-dev' | 'github') => {
    setIntegrationMenuId(null)
    if (selectedIntegration === id) {
      selectIntegration(null)
    } else {
      if (id === 'azure-dev') selectIntegration('azure-dev')
      else openGitHubConfiguration()
    }
  }

  const handleMenuAction = (id: 'azure-dev' | 'github', action: 'disconnect' | 'reconnect' | 'delete') => {
    setIntegrationMenuId(null)
    setPendingConfirmation({ integrationId: id, action })
  }

  const handleConfirmationAction = () => {
    if (!pendingConfirmation) return

    if (pendingConfirmation.action === 'disconnect') {
      if (pendingConfirmation.integrationId === 'azure-dev') setAzureDevConnected(false)
      else {
        setSavedGitHubConfiguration(current => current ? { ...current, connected: false } : current)
        setGitHubDraft(current => ({ ...current, connected: false }))
      }
    }

    if (pendingConfirmation.action === 'reconnect') {
      if (pendingConfirmation.integrationId === 'azure-dev') {
        setAzureDevConnected(false)
        setAzureDevConnectionMessage('Use Test Connection to verify the current credentials.')
      }
      else {
        setSavedGitHubConfiguration(current => current ? { ...current, connected: true } : current)
        setGitHubDraft(current => ({ ...current, connected: true }))
      }
    }

    if (pendingConfirmation.action === 'delete') {
      if (pendingConfirmation.integrationId === 'azure-dev') {
        setAzureDevDeleted(true)
        if (selectedIntegration === 'azure-dev') selectIntegration('catalog')
        cancelAzureChanges()
      } else {
        setSavedGitHubConfiguration(null)
        setGitHubDraft({ ...initialGitHubConfiguration })
        if (selectedIntegration === 'github') selectIntegration('catalog')
        setShowGitHubToken(false)
      }
    }

    setPendingConfirmation(null)
  }

  // Routes catalog actions while leaving integrations without forms in the gallery.
  const configureIntegration = (id: typeof integrationCatalog[number]['id']) => {
    if (id === 'azure-dev') selectIntegration('azure-dev')
    else if (id === 'github') openGitHubConfiguration()
    else showToast(`${integrationCatalog.find(item => item.id === id)?.name} configuration is not available yet`)
  }

  // Applies a single GitHub draft field update without mutating saved configuration.
  function updateGitHubDraft<K extends keyof GitHubConfiguration>(field: K, value: GitHubConfiguration[K]) {
    setGitHubDraft(current => ({ ...current, [field]: value }))
  }

  // Toggles an item in a GitHub array field while preventing duplicate selections.
  const toggleGitHubOption = (field: 'contentTypes' | 'fileTypes', value: string) => {
    const selected = githubDraft[field]
    updateGitHubDraft(field, selected.includes(value) ? selected.filter(option => option !== value) : [...selected, value])
  }

  return <div className="flex min-w-0 flex-1 flex-col overflow-hidden md:flex-row">
    <aside aria-label="Configuration navigation" className="shrink-0 border-b border-[#e6ecf5] bg-white px-4 py-5 md:w-[230px] md:border-b-0 md:border-r md:py-6">
      <div className="flex items-center gap-1">
        <button type="button" onClick={onBack} className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-50 hover:text-blue-600" aria-label="Back to previous page"><ChevronLeft size={17} /></button>
        <h1 className="text-lg font-bold tracking-[-.02em] text-slate-900">Configuration</h1>
      </div>
      <p className="mt-1 text-[11px] leading-5 text-slate-500">Manage connected tools and services.</p>
      <nav className="mt-5" aria-label="Integrations">
        <p className="mb-2 px-3 text-[9px] font-bold uppercase tracking-[.12em] text-slate-400">Integrations</p>
        {!azureDevDeleted && <div ref={integrationMenuId === 'azure-dev' ? integrationMenuRef : undefined} className="relative">
          <button type="button" onClick={() => handleIntegrationRowOpen('azure-dev')} aria-current={selectedIntegration === 'azure-dev' ? 'page' : undefined} className={`flex min-h-10 w-full items-center gap-2.5 rounded-xl px-3 py-2 pr-8 text-left text-[12px] font-medium ${selectedIntegration === 'azure-dev' ? 'bg-[#eef4ff] text-blue-600 shadow-[0_2px_8px_rgba(37,99,235,.05)]' : 'text-slate-600 hover:bg-slate-50'}`}>
            <CloudCog size={17} strokeWidth={1.8} /><span className="min-w-0 flex-1"><span className="block truncate">Azure Dev</span><span className={`mt-0.5 flex items-center gap-1 text-[9px] font-semibold ${azureDevConnected ? 'text-emerald-600' : 'text-slate-500'}`}><span className={`h-1.5 w-1.5 rounded-full ${azureDevConnected ? 'bg-emerald-500' : 'bg-slate-400'}`} />{azureDevConnected ? 'Connected' : 'Disconnected'}</span></span>
          </button>
          <button type="button" aria-label="More actions for Azure Dev" aria-expanded={integrationMenuId === 'azure-dev'} onClick={event => { event.stopPropagation(); setIntegrationMenuId(current => current === 'azure-dev' ? null : 'azure-dev') }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 text-lg leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-700">⋮</button>
          {integrationMenuId === 'azure-dev' && <div className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-[0_16px_40px_rgba(15,23,42,.12)]">
            <button type="button" onClick={event => { event.stopPropagation(); handleIntegrationRowOpen('azure-dev') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-slate-700 hover:bg-slate-50">Edit Configuration</button>
            <button type="button" onClick={event => { event.stopPropagation(); handleMenuAction('azure-dev', azureDevConnected ? 'disconnect' : 'reconnect') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-slate-700 hover:bg-slate-50">{azureDevConnected ? 'Disconnect' : 'Reconnect'}</button>
            <div className="my-1 h-px bg-slate-200" />
            <button type="button" onClick={event => { event.stopPropagation(); handleMenuAction('azure-dev', 'delete') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-red-600 hover:bg-red-50">Delete Configuration</button>
          </div>}
        </div>}
        {savedGitHubConfiguration && <div ref={integrationMenuId === 'github' ? integrationMenuRef : undefined} className="relative mt-1">
          <button type="button" onClick={() => handleIntegrationRowOpen('github')} aria-current={selectedIntegration === 'github' ? 'page' : undefined} className={`flex min-h-10 w-full items-center gap-2.5 rounded-xl px-3 py-2 pr-8 text-left text-[12px] font-medium ${selectedIntegration === 'github' ? 'bg-[#eef4ff] text-blue-600 shadow-[0_2px_8px_rgba(37,99,235,.05)]' : 'text-slate-600 hover:bg-slate-50'}`}>
            <Github size={17} strokeWidth={1.8} /><span className="min-w-0 flex-1"><span className="block truncate">GitHub</span><span className={`mt-0.5 flex items-center gap-1 text-[9px] font-semibold ${savedGitHubConfiguration.connected ? 'text-emerald-600' : 'text-slate-500'}`}><span className={`h-1.5 w-1.5 rounded-full ${savedGitHubConfiguration.connected ? 'bg-emerald-500' : 'bg-slate-400'}`} />{savedGitHubConfiguration.connected ? 'Connected' : 'Disconnected'}</span></span>
          </button>
          <button type="button" aria-label="More actions for GitHub" aria-expanded={integrationMenuId === 'github'} onClick={event => { event.stopPropagation(); setIntegrationMenuId(current => current === 'github' ? null : 'github') }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 text-lg leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-700">⋮</button>
          {integrationMenuId === 'github' && <div className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-[0_16px_40px_rgba(15,23,42,.12)]">
            <button type="button" onClick={event => { event.stopPropagation(); handleIntegrationRowOpen('github') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-slate-700 hover:bg-slate-50">Edit Configuration</button>
            <button type="button" onClick={event => { event.stopPropagation(); handleMenuAction('github', savedGitHubConfiguration.connected ? 'disconnect' : 'reconnect') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-slate-700 hover:bg-slate-50">{savedGitHubConfiguration.connected ? 'Disconnect' : 'Reconnect'}</button>
            <div className="my-1 h-px bg-slate-200" />
            <button type="button" onClick={event => { event.stopPropagation(); handleMenuAction('github', 'delete') }} className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-[12px] font-medium text-red-600 hover:bg-red-50">Delete Configuration</button>
          </div>}
        </div>}
        <button type="button" onClick={() => selectIntegration(selectedIntegration === 'catalog' ? null : 'catalog')} aria-current={selectedIntegration === 'catalog' ? 'page' : undefined} className={`mt-1 flex h-10 w-full items-center gap-2.5 rounded-xl px-3 text-left text-[12px] font-semibold ${selectedIntegration === 'catalog' ? 'bg-[#eef4ff] text-blue-600' : 'text-slate-600 hover:bg-slate-50 hover:text-blue-600'}`}><Plus size={16} />Add Integration</button>
      </nav>
    </aside>

    <section className="min-w-0 flex-1 overflow-y-auto bg-slate-50 px-5 py-5 sm:px-8 lg:px-10">
      {selectedIntegration === 'azure-dev' && (
      <div className="mx-auto max-w-4xl">
        <h2 className="text-xl font-bold tracking-[-.03em] text-slate-900">Azure Dev Configuration</h2>
        <p className="mt-1 text-xs text-slate-500">Manage your Azure Dev settings and connections.</p>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Connection</h3>
          <p className="mt-1 text-[11px] text-slate-500">Connect to your Azure Dev organization.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Organization URL">
              <input className="field w-full" type="url" value={organizationUrl} onChange={event => updateAzureCredentials('organizationUrl', event.target.value)} placeholder="https://dev.azure.com/organization" />
            </Field>
            <Field label="Personal Access Token">
              <div className="relative">
                <input className="field w-full pr-10" type={showToken ? 'text' : 'password'} value={personalAccessToken} onChange={event => updateAzureCredentials('personalAccessToken', event.target.value)} autoComplete="off" />
                <button type="button" onClick={() => setShowToken(current => !current)} className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-50 hover:text-blue-600" aria-label={showToken ? 'Hide personal access token' : 'Show personal access token'}>
                  {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={testingAzureDevConnection} onClick={handleTestAzureConnection}>{testingAzureDevConnection ? 'Testing...' : 'Test Connection'}</Button>
            {azureDevConnected && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">Connected</span>}
          </div>
          <p className={`mt-2 text-[11px] ${azureDevConnected ? 'text-emerald-700' : 'text-slate-500'}`}>{azureDevConnectionMessage}</p>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Source</h3>
          <p className="mt-1 text-[11px] text-slate-500">Select the data you want to import.</p>
          <div className="mt-4">
            <Field label="Project">
              <select className="field w-full sm:max-w-md" value={selectedProject} disabled={!azureDevConnected} onChange={event => setSelectedProject(event.target.value)}>
                {!azureDevProjects.length && <option value="">No Azure projects available</option>}
                {azureDevProjects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            </Field>
          </div>
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            <CheckboxGroup label="Work Item Types" options={['Bug', 'User Story', 'Task', 'Epic']} selected={workItemTypes} onToggle={value => toggleOption(value, workItemTypes, setWorkItemTypes)} />
            <CheckboxGroup label="States" options={['New', 'Active', 'Resolved', 'Closed']} selected={states} onToggle={value => toggleOption(value, states, setStates)} />
          </div>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Content</h3>
          <p className="mt-1 text-[11px] text-slate-500">Map Azure Dev fields to your knowledge base.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Title Field">
              <select className="field w-full" value={titleField} onChange={event => setTitleField(event.target.value)}>
                {fieldOptions.map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Content Field">
              <select className="field w-full" value={contentField} onChange={event => setContentField(event.target.value)}>
                {fieldOptions.map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Metadata Fields">
              <select multiple className="field min-h-28 w-full py-2" value={metadataFields} onChange={event => setMetadataFields(Array.from(event.target.selectedOptions, option => option.value))} aria-describedby="metadata-fields-help">
                {fieldOptions.map(option => <option key={option} value={option}>{option}</option>)}
              </select>
              <span id="metadata-fields-help" className="mt-1.5 block text-[11px] font-normal text-slate-500">Use Ctrl or Command to select multiple fields.</span>
            </Field>
          </div>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Sync</h3>
          <p className="mt-1 text-[11px] text-slate-500">Configure how often data should be synchronized.</p>
          <fieldset className="mt-4">
            <legend className="text-[12px] font-medium text-slate-700">Sync Mode</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <RadioOption checked={syncMode === 'manual'} label="Manual" description="Sync only when you click Sync Now." onChange={() => setSyncMode('manual')} />
              <RadioOption checked={syncMode === 'scheduled'} label="Scheduled" description="Sync automatically on a schedule." onChange={() => setSyncMode('scheduled')} />
            </div>
          </fieldset>
          <div className="mt-4 max-w-sm">
            <Field label="Frequency">
              <select className="field w-full" value={frequency} disabled={syncMode === 'manual'} onChange={event => setFrequency(event.target.value)}>
                <option>Every 1 hour</option>
                <option>Every 6 hours</option>
                <option>Every 12 hours</option>
                <option>Every 24 hours</option>
              </select>
            </Field>
          </div>
          <label className="mt-4 flex items-start gap-2.5 text-[12px] text-slate-700">
            <input type="checkbox" checked={syncChangedOnly} onChange={event => setSyncChangedOnly(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-blue-600" />
            <span><span className="font-medium">Sync only changed work items</span><span className="mt-0.5 block text-[11px] text-slate-500">Only import items that have been created or updated.</span></span>
          </label>
        </Card>

        <Card className="my-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Actions</h3>
          <p className="mt-1 text-[11px] text-slate-500">Review and save your configuration.</p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 rounded-xl border border-slate-100 bg-slate-50 p-3 text-[11px] sm:grid-cols-2">
            <SummaryItem label="Organization" value={organizationSummary} />
            <SummaryItem label="Project" value={selectedProject || 'Not selected'} />
            <SummaryItem label="Types" value={workItemTypes.join(', ') || 'None'} />
            <SummaryItem label="States" value={states.join(', ') || 'None'} />
            <SummaryItem label="Sync" value={syncMode === 'manual' ? 'Manual' : frequency} />
          </dl>
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={cancelAzureChanges}>Cancel</Button>
            <Button type="button" disabled={!azureDevConnected} onClick={() => showToast('Azure DevOps connection verified. Sync configuration persistence is not available yet.')}>Save &amp; Sync</Button>
          </div>
        </Card>
      </div>
      )}
      {selectedIntegration === 'catalog' && <div className="mx-auto max-w-4xl">
        <h2 className="text-xl font-bold tracking-[-.03em] text-slate-900">Add Integration</h2>
        <p className="mt-1 text-xs text-slate-500">Connect Docsense with the tools your team already uses.</p>
        <div className="relative mt-4 max-w-md"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={integrationSearch} onChange={event => setIntegrationSearch(event.target.value)} placeholder="Search integrations" className="field h-10 w-full pl-9" aria-label="Search integrations" /></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {visibleIntegrations.map(integration => {
            const Icon = integration.icon
            return <Card key={integration.id} className="flex min-h-36 flex-col border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
              <div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-600"><Icon size={19} /></span><div className="min-w-0"><h3 className="text-sm font-semibold text-slate-900">{integration.name}</h3><p className="mt-1 text-[11px] leading-5 text-slate-500">{integration.description}</p></div></div>
              <button type="button" onClick={() => configureIntegration(integration.id)} className="mt-auto self-start pt-4 text-[11px] font-semibold text-blue-600 hover:text-blue-700">Configure <span aria-hidden="true">→</span></button>
            </Card>
          })}
        </div>
        {!visibleIntegrations.length && <p className="py-10 text-center text-xs text-slate-400">No integrations found.</p>}
      </div>}
      {selectedIntegration === 'github' && <div className="mx-auto max-w-4xl">
        <h2 className="text-xl font-bold tracking-[-.03em] text-slate-900">Configure GitHub</h2>
        <p className="mt-1 text-xs text-slate-500">Connect GitHub repositories as a knowledge source.</p>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Connection</h3>
          <p className="mt-1 text-[11px] text-slate-500">Connect your GitHub account or organization.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="GitHub Account / Organization">
              <input className="field w-full" value={githubDraft.organization} onChange={event => updateGitHubCredentials('organization', event.target.value)} placeholder="adevtech" />
            </Field>
            <Field label="Personal Access Token">
              <div className="relative">
                <input className="field w-full pr-10" type={showGitHubToken ? 'text' : 'password'} value={githubDraft.personalAccessToken} onChange={event => updateGitHubCredentials('personalAccessToken', event.target.value)} autoComplete="off" />
                <button type="button" onClick={() => setShowGitHubToken(current => !current)} className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-50 hover:text-blue-600" aria-label={showGitHubToken ? 'Hide personal access token' : 'Show personal access token'}>
                  {showGitHubToken ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={testingGitHubConnection} onClick={handleTestGitHubConnection}>{testingGitHubConnection ? 'Testing...' : 'Test Connection'}</Button>
            {githubDraft.connected && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">✓ Connected</span>}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Frontend-only preview: credentials are not sent or verified.</p>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Source</h3>
          <p className="mt-1 text-[11px] text-slate-500">Select repository content to import.</p>
          <fieldset disabled={!githubDraft.connected} className="mt-4 disabled:cursor-not-allowed disabled:opacity-50">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Repository">
                <select className="field w-full" value={githubDraft.repository} onChange={event => updateGitHubDraft('repository', event.target.value)}>
                  {['docsense-ai', 'docsense-api', 'internal-tools', 'documentation'].map(option => <option key={option}>{option}</option>)}
                </select>
              </Field>
              <Field label="Branch">
                <select className="field w-full" value={githubDraft.branch} onChange={event => updateGitHubDraft('branch', event.target.value)}>
                  {['main', 'develop', 'staging', 'release'].map(option => <option key={option}>{option}</option>)}
                </select>
              </Field>
            </div>
            <LabeledCheckboxGroup label="Content to Import" options={[
              ['source_files', 'Source files'], ['readme_markdown', 'README / Markdown'], ['documentation', 'Documentation'], ['issues', 'Issues'], ['pull_requests', 'Pull Requests'],
            ]} selected={githubDraft.contentTypes} onToggle={value => toggleGitHubOption('contentTypes', value)} />
          </fieldset>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">File Filters</h3>
          <p className="mt-1 text-[11px] text-slate-500">Choose which repository files are included in the knowledge source.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Include Paths">
              <input className="field w-full" value={githubDraft.includePaths} onChange={event => updateGitHubDraft('includePaths', event.target.value)} aria-describedby="github-include-help" />
              <span id="github-include-help" className="mt-1.5 block text-[11px] font-normal text-slate-500">Only files matching these paths will be imported.</span>
            </Field>
            <Field label="Exclude Paths">
              <input className="field w-full" value={githubDraft.excludePaths} onChange={event => updateGitHubDraft('excludePaths', event.target.value)} aria-describedby="github-exclude-help" />
              <span id="github-exclude-help" className="mt-1.5 block text-[11px] font-normal text-slate-500">Files matching these paths will be ignored.</span>
            </Field>
          </div>
          <div className="mt-4"><CheckboxGroup label="File Types" options={['.md', '.txt', '.ts', '.tsx', '.js', '.py', '.json']} selected={githubDraft.fileTypes} onToggle={value => toggleGitHubOption('fileTypes', value)} /></div>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Content Mapping</h3>
          <p className="mt-1 text-[11px] text-slate-500">Map repository files to your knowledge base.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Title">
              <select className="field w-full" value={githubDraft.titleMapping} onChange={event => updateGitHubDraft('titleMapping', event.target.value)}>
                <option value="file_name">File name</option><option value="file_path">File path</option><option value="file_name_path">File name / Path</option>
              </select>
            </Field>
            <Field label="Content">
              <select className="field w-full" value={githubDraft.contentMapping} onChange={event => updateGitHubDraft('contentMapping', event.target.value)}><option value="file_content">File content</option></select>
            </Field>
            <Field label="Metadata">
              <select multiple className="field min-h-28 w-full py-2" value={githubDraft.metadataFields} onChange={event => updateGitHubDraft('metadataFields', Array.from(event.target.selectedOptions, option => option.value))} aria-describedby="github-metadata-help">
                <option value="repository">Repository</option><option value="branch">Branch</option><option value="path">Path</option><option value="commit_sha">Commit SHA</option>
              </select>
              <span id="github-metadata-help" className="mt-1.5 block text-[11px] font-normal text-slate-500">Use Ctrl or Command to select multiple fields.</span>
            </Field>
          </div>
        </Card>

        <Card className="mt-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Sync</h3>
          <p className="mt-1 text-[11px] text-slate-500">Configure how often repository data should be synchronized.</p>
          <fieldset className="mt-4">
            <legend className="text-[12px] font-medium text-slate-700">Sync Mode</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <RadioOption checked={githubDraft.syncMode === 'manual'} label="Manual" description="Sync only when you click Sync Now." onChange={() => updateGitHubDraft('syncMode', 'manual')} />
              <RadioOption checked={githubDraft.syncMode === 'scheduled'} label="Scheduled" description="Sync automatically on a schedule." onChange={() => updateGitHubDraft('syncMode', 'scheduled')} />
            </div>
          </fieldset>
          {githubDraft.syncMode === 'scheduled' && <div className="mt-4 max-w-sm">
            <Field label="Frequency">
              <select className="field w-full" value={githubDraft.frequency} onChange={event => updateGitHubDraft('frequency', event.target.value)}>
                <option value="1h">Every 1 hour</option><option value="6h">Every 6 hours</option><option value="12h">Every 12 hours</option><option value="daily">Daily</option>
              </select>
            </Field>
          </div>}
          <label className="mt-4 flex items-start gap-2.5 text-[12px] text-slate-700">
            <input type="checkbox" checked={githubDraft.incrementalSync} onChange={event => updateGitHubDraft('incrementalSync', event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-blue-600" />
            <span><span className="font-medium">Sync only changed files</span><span className="mt-0.5 block text-[11px] text-slate-500">Only import files that have been added or updated.</span></span>
          </label>
        </Card>

        <Card className="my-4 border-[#e6ecf5] p-4 shadow-[0_5px_18px_rgba(37,99,235,.04)]">
          <h3 className="text-sm font-semibold text-slate-900">Actions</h3>
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="secondary" disabled={savingGitHubConfiguration} onClick={() => { setGitHubDraft({ ...(savedGitHubConfiguration ?? initialGitHubConfiguration) }); selectIntegration('catalog') }}>Cancel</Button>
            <Button type="button" disabled={savingGitHubConfiguration} onClick={handleSaveGitHubConfiguration}>{savingGitHubConfiguration ? 'Saving...' : 'Save & Sync'}</Button>
          </div>
        </Card>
      </div>}
    </section>

    {pendingConfirmation && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_18px_50px_rgba(15,23,42,.18)]">
        <h3 className="text-sm font-semibold text-slate-900">{pendingConfirmation.action === 'delete' ? 'Delete configuration?' : pendingConfirmation.action === 'disconnect' ? 'Disconnect integration?' : 'Reconnect integration?'}</h3>
        <p className="mt-2 text-[12px] leading-5 text-slate-600">
          {pendingConfirmation.action === 'delete'
            ? `Delete the saved ${pendingConfirmation.integrationId === 'azure-dev' ? 'Azure Dev' : 'GitHub'} configuration? This removes it from the sidebar and clears its frontend settings.`
            : pendingConfirmation.action === 'disconnect'
              ? `Disconnect ${pendingConfirmation.integrationId === 'azure-dev' ? 'Azure Dev' : 'GitHub'} and keep the saved configuration for later?`
              : `Reconnect ${pendingConfirmation.integrationId === 'azure-dev' ? 'Azure Dev' : 'GitHub'} and restore the saved configuration?`}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => setPendingConfirmation(null)}>Cancel</Button>
          <Button type="button" onClick={handleConfirmationAction}>{pendingConfirmation.action === 'delete' ? 'Delete' : pendingConfirmation.action === 'disconnect' ? 'Disconnect' : 'Reconnect'}</Button>
        </div>
      </div>
    </div>}

  </div>
}

// Keeps form labels and controls consistent while allowing integrations to add different control types later.
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-[12px] font-medium text-slate-700">
    <span className="mb-2 block">{label}</span>
    {children}
  </label>
}

// Renders a compact, accessible group of checkbox options.
function CheckboxGroup({ label, options, selected, onToggle }: { label: string; options: string[]; selected: string[]; onToggle: (value: string) => void }) {
  return <fieldset>
    <legend className="text-[12px] font-medium text-slate-700">{label}</legend>
    <div className="mt-2 grid grid-cols-2 gap-2">
      {options.map(option => <label key={option} className="flex items-center gap-2 text-[12px] text-slate-600">
        <input type="checkbox" checked={selected.includes(option)} onChange={() => onToggle(option)} className="h-4 w-4 rounded border-slate-300 accent-blue-600" />
        {option}
      </label>)}
    </div>
  </fieldset>
}

// Renders checkbox labels independently from their persisted integration values.
function LabeledCheckboxGroup({ label, options, selected, onToggle }: { label: string; options: ReadonlyArray<readonly [string, string]>; selected: string[]; onToggle: (value: string) => void }) {
  return <fieldset className="mt-4">
    <legend className="text-[12px] font-medium text-slate-700">{label}</legend>
    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
      {options.map(([value, optionLabel]) => <label key={value} className="flex items-center gap-2 text-[12px] text-slate-600">
        <input type="checkbox" checked={selected.includes(value)} onChange={() => onToggle(value)} className="h-4 w-4 rounded border-slate-300 accent-blue-600" />
        {optionLabel}
      </label>)}
    </div>
  </fieldset>
}

// Renders one sync-mode choice with its explanatory text.
function RadioOption({ checked, label, description, onChange }: { checked: boolean; label: string; description: string; onChange: () => void }) {
  return <label className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 ${checked ? 'border-blue-200 bg-blue-50/60' : 'border-slate-200 bg-white'}`}>
    <input type="radio" name="sync-mode" checked={checked} onChange={onChange} className="mt-0.5 h-4 w-4 accent-blue-600" />
    <span><span className="block text-[12px] font-semibold text-slate-800">{label}</span><span className="mt-0.5 block text-[11px] text-slate-500">{description}</span></span>
  </label>
}

// Renders a label-value pair in the configuration summary.
function SummaryItem({ label, value }: { label: string; value: string }) {
  return <div className="flex min-w-0 gap-2"><dt className="shrink-0 font-semibold text-slate-600">{label}:</dt><dd className="truncate text-slate-500" title={value}>{value}</dd></div>
}
