export type SourceItem = {
  title: string | null
  url: string
  source_name?: string | null
  published_at?: string | null
}

export type ToolCallTrace = {
  name: string
  mcp_path: string
  arguments: Record<string, unknown>
  mcp_http_status: number
  mcp_response_meta: Record<string, unknown>
  article_count: number
  error: string | null
}

export type ChatResponse = {
  reply_markdown: string
  brief: string
  sources: SourceItem[]
  trace: { tool_calls: ToolCallTrace[] }
}
