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
} from "lucide-react"

import { ServiceHealth } from "@/components/layout/service-health"
import { HrChatbotWidget } from "@/components/hr/chatbot/hr-chatbot-widget"
import { HrHeaderUser } from "@/components/hr/layout/hr-header-user"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
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
      <SidebarHeader className="p-3.5">
        <Link
          href="/hr"
          className="flex min-h-10 items-center gap-3 rounded-lg px-2 outline-none ring-sidebar-ring transition-colors hover:bg-sidebar-accent focus-visible:ring-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
          onClick={() => {
            if (isMobile) setOpenMobile(false)
          }}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-2xs">
            <Building2 className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <span className="block truncate text-sm font-semibold tracking-tight">HR Portal</span>
            <span className="block truncate text-xs text-sidebar-foreground/70">
              Nhân sự và tri thức
            </span>
          </span>
        </Link>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent className="px-1 py-2">
        <Suspense fallback={<HrNavigationLinks />}>
          <HrNavigation />
        </Suspense>
        <SidebarSeparator className="my-2" />
        <SidebarGroup>
          <SidebarGroupLabel>Công cụ liên kết</SidebarGroupLabel>
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
      <SidebarFooter className="space-y-2.5 p-3.5">
        <div className="group-data-[collapsible=icon]:hidden">
          <ServiceHealth apiBaseUrl={apiBaseUrl} />
        </div>
        <p className="px-2 text-[11px] leading-5 text-sidebar-foreground/65 group-data-[collapsible=icon]:hidden">
          Không gian hỏi đáp chính nằm tại /chat.
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
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
        {chatbotSlot ?? <HrChatbotWidget apiBaseUrl={apiBaseUrl} />}
      </SidebarInset>
    </SidebarProvider>
  )
}
