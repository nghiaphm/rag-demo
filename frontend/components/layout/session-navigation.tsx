"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { LoaderCircle, MessageSquare, Plus, RotateCcw } from "lucide-react"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useSessions } from "@/hooks/use-sessions"

function UnconfiguredSessions() {
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Phiên trò chuyện</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton disabled tooltip="Chưa cấu hình API">
              <Plus aria-hidden="true" />
              <span>Cuộc trò chuyện mới</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <p className="px-2 pt-2 text-xs leading-5 text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
          Chưa cấu hình API.
        </p>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

function ConfiguredSessions({ apiBaseUrl }: { apiBaseUrl: string }) {
  const pathname = usePathname()
  const router = useRouter()
  const { isMobile, setOpenMobile } = useSidebar()
  const { sessions, total, status, isCreating, error, reload, createNew } = useSessions(apiBaseUrl)

  async function newChat() {
    const session = await createNew()
    if (!session) return
    if (isMobile) setOpenMobile(false)
    router.push(`/chat/${session.session_id}`)
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Phiên trò chuyện</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              variant="outline"
              tooltip="Cuộc trò chuyện mới"
              disabled={status === "loading" || isCreating}
              onClick={() => void newChat()}
            >
              {isCreating ? (
                <LoaderCircle className="animate-spin" aria-hidden="true" />
              ) : (
                <Plus aria-hidden="true" />
              )}
              <span>{isCreating ? "Đang tạo phiên…" : "Cuộc trò chuyện mới"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>

          {status === "loading" && (
            <SidebarMenuItem>
              <SidebarMenuButton disabled>
                <LoaderCircle className="animate-spin" aria-hidden="true" />
                <span>Đang tải phiên…</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}

          {status === "error" && (
            <SidebarMenuItem>
              <SidebarMenuButton type="button" onClick={() => void reload()} tooltip="Tải lại phiên">
                <RotateCcw aria-hidden="true" />
                <span>Tải lại danh sách</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}

          {status === "ready" && sessions.length === 0 && (
            <SidebarMenuItem>
              <p className="px-2 py-2 text-xs leading-5 text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
                Chưa có phiên trò chuyện.
              </p>
            </SidebarMenuItem>
          )}

          {sessions.map((session) => {
            const href = `/chat/${session.session_id}`
            const active = pathname === href
            return (
              <SidebarMenuItem key={session.session_id}>
                <SidebarMenuButton
                  isActive={active}
                  tooltip={session.title}
                  render={
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      onClick={() => {
                        if (isMobile) setOpenMobile(false)
                      }}
                    />
                  }
                >
                  <MessageSquare aria-hidden="true" />
                  <span>{session.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
        {error && (
          <p role="alert" className="px-2 pt-2 text-xs leading-5 text-destructive group-data-[collapsible=icon]:hidden">
            {error}
          </p>
        )}
        {status === "ready" && total > sessions.length && (
          <p className="px-2 pt-2 text-xs text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
            Hiển thị {sessions.length}/{total} phiên.
          </p>
        )}
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

export function SessionNavigation({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  return apiBaseUrl
    ? <ConfiguredSessions apiBaseUrl={apiBaseUrl} />
    : <UnconfiguredSessions />
}
