import React from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
try {
  const { default: App } = await server.ssrLoadModule('/src/App.tsx')
  const { AppProvider } = await server.ssrLoadModule('/src/context/AppContext.tsx')
  const html = renderToString(React.createElement(AppProvider, null, React.createElement(App)))
  console.log(`SSR render succeeded: ${html.length} characters`)
} finally {
  await server.close()
}
