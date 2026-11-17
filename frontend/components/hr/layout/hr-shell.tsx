"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Suspense, type ReactNode } from "react"
import {
  ArrowLeft,
  BookOpen,
  Building2,
  Files,
  LayoutDashboard,
  MessageSquareText,
  X,
} from "lucide-react"

import { ServiceHealth } from "@/components/layout/service-health"
import { HrHeaderUser } from "@/components/hr/layout/hr-header-user"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { Button } from "@/components/ui/button"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar"
import type { HrPageRoute, HrUserProfile } from "@/types/hr"

export const hrNavigationItems: readonly {
  href: HrPageRoute
  label: string
  icon: typeof LayoutDashboard
  exact?: boolean
}[] = [
  {
    href: "/hr",
    label: "Tổng quan HR",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    href: "/hr/documents",
    label: "Tài liệu nhân sự",
    icon: Files,
  },
  {
    href: "/hr/guide",
    label: "Hướng dẫn sử dụng",
    icon: BookOpen,
  },
] as const

export function matchesHrRoute(pathname: string, href: HrPageRoute, exact = false): boolean {
  if (exact) return pathname === href
  return pathname === href || pathname.startsWith(`${href}/`)
}

function HrNavigationLinks({ pathname }: { pathname?: string }) {
  const { isMobile, setOpenMobile } = useSidebar()

  return (
    <nav aria-label="Điều hướng HR Portal">
      <SidebarGroup>
        <SidebarGroupLabel>Cổng nhân sự</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {hrNavigationItems.map((item) => {
              const isActive = pathname
                ? matchesHrRoute(pathname, item.href, item.exact)
                : false
              const Icon = item.icon

              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={item.label}
                    render={
                      <Link
                        href={item.href}
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => {
                          if (isMobile) setOpenMobile(false)
                        }}
                      />
                    }
                  >
                    <Icon aria-hidden="true" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )
            })}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </nav>
  )
}

function HrNavigation() {
  const pathname = usePathname()
  return <HrNavigationLinks pathname={pathname} />
}

function HrSidebar({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { isMobile, setOpenMobile } = useSidebar()
  const { openWidget } = useHrChatbot()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-3">
        <Link
          href="/hr"
          className="flex min-h-10 items-center gap-3 rounded-lg px-2 outline-none ring-sidebar-ring transition-colors hover:bg-sidebar-accent focus-visible:ring-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          onClick={() => {
            if (isMobile) setOpenMobile(false)
          }}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
            <Building2 className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <span className="block truncate text-sm font-semibold">HR Portal</span>
            <span className="block truncate text-xs text-sidebar-foreground/65">
              Demo tích hợp RAG
            </span>
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        <Suspense fallback={<HrNavigationLinks />}>
          <HrNavigation />
        </Suspense>
        <SidebarSeparator />
        <SidebarGroup>
          <SidebarGroupLabel>Công cụ & Hệ thống</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  type="button"
                  tooltip="Mở Trợ lý HR"
                  onClick={() => {
                    if (isMobile) setOpenMobile(false)
                    openWidget()
                  }}
                >
                  <MessageSquareText aria-hidden="true" />
                  <span>Trợ lý chính sách HR</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Về RAG Workspace"
                  render={
                    <Link
                      href="/chat"
                      onClick={() => {
                        if (isMobile) setOpenMobile(false)
                      }}
                    />
                  }
                >
                  <ArrowLeft aria-hidden="true" />
                  <span>Về RAG Workspace</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="space-y-2 p-3">
        <div className="group-data-[collapsible=icon]:hidden">
          <ServiceHealth apiBaseUrl={apiBaseUrl} />
        </div>
        <p className="px-2 text-xs leading-5 text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
          RAG Workspace vẫn là giao diện chính tại /chat.
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

function DefaultChatbotLauncher() {
  const { isOpen, pageContext, draftPrompt, openWidget, closeWidget } = useHrChatbot()

  return (
    <>
      <div className="fixed right-5 bottom-5 z-30">
        <Button
          type="button"
          size="lg"
          className="rounded-full shadow-lg"
          aria-expanded={isOpen}
          aria-label="Mở Trợ lý HR"
          onClick={() => (isOpen ? closeWidget() : openWidget())}
        >
          <MessageSquareText className="size-4" aria-hidden="true" />
          <span>Trợ lý HR</span>
        </Button>
      </div>

      {isOpen && (
        <aside
          aria-label="Khung Trợ lý HR"
          className="fixed right-5 bottom-20 z-40 w-[calc(100vw-2.5rem)] max-w-md rounded-xl border bg-background p-4 shadow-xl"
        >
          <div className="flex items-start justify-between gap-2 border-b pb-3">
            <div>
              <p className="text-sm font-semibold">Trợ lý chính sách HR</p>
              <p className="text-xs text-muted-foreground">
                {pageContext?.title
                  ? `Ngữ cảnh hiện tại: ${pageContext.title}`
                  : "Sẵn sàng kết nối RAG Chatbot ở Phase H4"}
              </p>
            </div>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label="Đóng Trợ lý HR"
              onClick={closeWidget}
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div className="mt-3 space-y-3 text-xs leading-5 text-muted-foreground">
            {draftPrompt && (
              <p className="rounded-lg border bg-muted/40 p-2 text-foreground">
                Câu hỏi gợi ý: {draftPrompt}
              </p>
            )}
            <p>
              Khung Chatbot nổi sẽ được nối trực tiếp với RAG Backend (ChatController + SSE) tại Phase H4.
            </p>
            <Button
              nativeButton={false}
              size="sm"
              className="w-full"
              render={<Link href="/chat" />}
            >
              Mở Chat đầy đủ tại RAG Workspace
            </Button>
          </div>
        </aside>
      )}
    </>
  )
}

export function HrShell({
  children,
  apiBaseUrl,
  user,
  chatbotSlot,
}: {
  children: ReactNode
  apiBaseUrl: string | null
  user?: HrUserProfile
  chatbotSlot?: ReactNode
}) {
  return (
    <SidebarProvider>
      <HrSidebar apiBaseUrl={apiBaseUrl} />
      <SidebarInset id="main-content" tabIndex={-1} className="min-h-svh min-w-0">
        <HrHeaderUser user={user} />
        <div className="flex min-h-0 flex-1 flex-col bg-muted/30 p-4 sm:p-6 lg:p-8">
          {children}
        </div>
        {chatbotSlot ?? <DefaultChatbotLauncher />}
      </SidebarInset>
    </SidebarProvider>
  )
}
