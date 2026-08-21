import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Application render failed', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return <main className="grid min-h-screen place-items-center bg-slate-50 p-6"><div className="w-full max-w-xl rounded-2xl border border-red-200 bg-white p-6 shadow-xl"><p className="text-xs font-bold uppercase tracking-wider text-red-600">Application error</p><h1 className="mt-2 text-xl font-bold text-slate-900">The dashboard could not start</h1><p className="mt-3 rounded-xl bg-red-50 p-4 font-mono text-xs leading-5 text-red-800">{this.state.error.message}</p><button onClick={()=>{localStorage.removeItem('rag-theme');window.location.reload()}} className="mt-5 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white">Reset theme and reload</button></div></main>
  }
}
