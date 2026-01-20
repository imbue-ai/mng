import { useEffect, useRef, useState, useCallback } from 'react'
import { Layout, Model, TabNode, TabSetNode, BorderNode, IJsonModel, Action, Actions, DockLocation, ITabSetRenderValues } from 'flexlayout-react'
import 'flexlayout-react/style/dark.css'

interface Config {
  terminalUrl: string
  defaultUrl: string
}

interface UrlInputState {
  isOpen: boolean
  value: string
  tabsetId: string | null
}

interface DropdownState {
  isOpen: boolean
  tabsetId: string | null
  x: number
  y: number
}

function UrlTab({ url }: { url: string }) {
  return (
    <div className="tab-content">
      <iframe src={url} title="URL Content" sandbox="allow-same-origin allow-scripts allow-forms allow-popups" />
    </div>
  )
}

function TerminalTab({ terminalUrl }: { terminalUrl: string }) {
  return (
    <div className="tab-content">
      <iframe src={terminalUrl} title="Terminal" />
    </div>
  )
}

function App() {
  const [model, setModel] = useState<Model | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [urlInput, setUrlInput] = useState<UrlInputState>({ isOpen: false, value: '', tabsetId: null })
  const [dropdown, setDropdown] = useState<DropdownState>({ isOpen: false, tabsetId: null, x: 0, y: 0 })
  const layoutRef = useRef<Layout>(null)
  const saveTimeoutRef = useRef<number | null>(null)
  const dropdownJustOpenedRef = useRef(false)

  useEffect(() => {
    Promise.all([
      fetch('/api/layout').then(r => r.json()),
      fetch('/api/config').then(r => r.json())
    ]).then(([layoutData, configData]) => {
      setConfig(configData)
      setModel(Model.fromJson(layoutData as IJsonModel))
    })
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!dropdown.isOpen) return

    const handleClickOutside = () => {
      // Ignore the click that opened the dropdown
      if (dropdownJustOpenedRef.current) {
        dropdownJustOpenedRef.current = false
        return
      }
      setDropdown(prev => ({ ...prev, isOpen: false }))
    }

    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [dropdown.isOpen])

  const saveLayout = useCallback((newModel: Model) => {
    if (saveTimeoutRef.current) {
      window.clearTimeout(saveTimeoutRef.current)
    }
    saveTimeoutRef.current = window.setTimeout(() => {
      fetch('/api/layout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newModel.toJson())
      })
    }, 500)
  }, [])

  const handleModelChange = useCallback((newModel: Model) => {
    saveLayout(newModel)
  }, [saveLayout])

  const handleAction = useCallback((action: Action) => {
    return action
  }, [])

  const addUrlTab = useCallback((url: string, tabsetId: string) => {
    if (!model) return
    model.doAction(Actions.addNode(
      {
        type: 'tab',
        name: new URL(url).hostname || 'URL',
        component: 'url',
        config: { url }
      },
      tabsetId,
      DockLocation.CENTER,
      -1
    ))
    saveLayout(model)
  }, [model, saveLayout])

  const addTerminalTab = useCallback((tabsetId: string) => {
    if (!model || !config) return
    model.doAction(Actions.addNode(
      {
        type: 'tab',
        name: 'Terminal',
        component: 'terminal',
        config: {}
      },
      tabsetId,
      DockLocation.CENTER,
      -1
    ))
    saveLayout(model)
  }, [model, config, saveLayout])

  const handlePlusClick = useCallback((tabsetId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    const rect = (event.target as HTMLElement).getBoundingClientRect()
    dropdownJustOpenedRef.current = true
    setDropdown({
      isOpen: true,
      tabsetId,
      x: rect.left,
      y: rect.bottom + 2
    })
  }, [])

  const handleNewUrlTab = useCallback(() => {
    if (!dropdown.tabsetId) return
    setDropdown(prev => ({ ...prev, isOpen: false }))
    setUrlInput({ isOpen: true, value: config?.defaultUrl || 'https://', tabsetId: dropdown.tabsetId })
  }, [config, dropdown.tabsetId])

  const handleNewTerminalTab = useCallback(() => {
    if (!dropdown.tabsetId) return
    addTerminalTab(dropdown.tabsetId)
    setDropdown(prev => ({ ...prev, isOpen: false }))
  }, [dropdown.tabsetId, addTerminalTab])

  const handleUrlSubmit = useCallback(() => {
    if (urlInput.value.trim() && urlInput.tabsetId) {
      addUrlTab(urlInput.value.trim(), urlInput.tabsetId)
    }
    setUrlInput({ isOpen: false, value: '', tabsetId: null })
  }, [urlInput.value, urlInput.tabsetId, addUrlTab])

  const handleUrlCancel = useCallback(() => {
    setUrlInput({ isOpen: false, value: '', tabsetId: null })
  }, [])

  const factory = useCallback((node: TabNode) => {
    const component = node.getComponent()
    const nodeConfig = node.getConfig() as Record<string, unknown> | undefined

    if (component === 'url') {
      const url = (nodeConfig?.url as string) || config?.defaultUrl || 'about:blank'
      return <UrlTab url={url} />
    }

    if (component === 'terminal') {
      return <TerminalTab terminalUrl={config?.terminalUrl || ''} />
    }

    return <div>Unknown component: {component}</div>
  }, [config])

  const onRenderTabSet = useCallback((node: TabSetNode | BorderNode, renderValues: ITabSetRenderValues) => {
    // Only add the + button to TabSetNodes, not BorderNodes
    if (node instanceof BorderNode) return
    renderValues.stickyButtons.push(
      <button
        key="add-tab"
        className="add-tab-button"
        title="Add tab"
        style={{
          background: 'transparent',
          border: 'none',
          color: '#ccc',
          fontSize: '18px',
          fontWeight: 'bold',
          cursor: 'pointer',
          padding: '0 8px',
          lineHeight: '1',
        }}
        onMouseDown={(e) => {
          e.stopPropagation()
          handlePlusClick(node.getId(), e)
        }}
      >
        +
      </button>
    )
  }, [handlePlusClick])

  if (!model || !config) {
    return <div style={{ color: '#fff', padding: 20 }}>Loading...</div>
  }

  return (
    <div className="app-container">
      <Layout
        ref={layoutRef}
        model={model}
        factory={factory}
        onAction={handleAction}
        onModelChange={handleModelChange}
        onRenderTabSet={onRenderTabSet}
      />
      {dropdown.isOpen && (
        <div
          className="tab-dropdown"
          style={{ left: dropdown.x, top: dropdown.y }}
          onClick={e => e.stopPropagation()}
        >
          <button onClick={handleNewUrlTab}>URL Tab</button>
          <button onClick={handleNewTerminalTab}>Terminal Tab</button>
        </div>
      )}
      {urlInput.isOpen && (
        <div className="url-input-overlay" onClick={handleUrlCancel}>
          <div className="url-input-dialog" onClick={e => e.stopPropagation()}>
            <h3>Enter URL</h3>
            <input
              type="text"
              value={urlInput.value}
              onChange={e => setUrlInput(prev => ({ ...prev, value: e.target.value }))}
              onKeyDown={e => {
                if (e.key === 'Enter') handleUrlSubmit()
                if (e.key === 'Escape') handleUrlCancel()
              }}
              autoFocus
              placeholder="https://example.com"
            />
            <div className="buttons">
              <button className="secondary" onClick={handleUrlCancel}>Cancel</button>
              <button className="primary" onClick={handleUrlSubmit}>Open</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
