export interface ScrollViewport {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/** Reader intent survives content growth; only a scroll event changes following. */
export class ChatScrollController {
  private viewport: ScrollViewport | null = null
  private following = true
  private unread = false
  private listeners = new Set<() => void>()
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  getSnapshot = () => this.unread
  private notify() { this.listeners.forEach(listener => listener()) }
  attach(viewport: ScrollViewport) {
    this.viewport = viewport
    this.following = true
    this.jump()
    return () => { this.viewport = null }
  }
  onScroll = () => {
    if (!this.viewport) return
    const { scrollHeight, clientHeight, scrollTop } = this.viewport
    this.following = scrollHeight - clientHeight - scrollTop <= 48
    if (this.following && this.unread) { this.unread = false; this.notify() }
  }
  contentChanged = () => {
    if (!this.viewport) return
    if (this.following) this.jump()
    else if (!this.unread) { this.unread = true; this.notify() }
  }
  jump = () => {
    if (!this.viewport) return
    // Instant updates preserve position and respect reduced motion during streaming.
    this.viewport.scrollTop = Math.max(0, this.viewport.scrollHeight - this.viewport.clientHeight)
    this.following = true
    if (this.unread) { this.unread = false; this.notify() }
  }
}
