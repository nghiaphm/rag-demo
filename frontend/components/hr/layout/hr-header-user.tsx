"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Suspense } from "react"
import { ArrowUpRight, MessageSquareText } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { SidebarTrigger } from "@/components/ui/sidebar"
import type { HrUserProfile } from "@/types/hr"

export const DEFAULT_HR_DEMO_USER: HrUserProfile = {
  name: "Minh Anh",
  roleTitle: "HR Specialist",
  department: "Phòng Nhân sự",
  email: "hr.demo@company.example",
  avatarInitials: "MA",
  isDemoProfile: true,
}

export function getHrRouteTitle(pathname: string): string {
  if (pathname === "/hr/documents" || pathname.startsWith("/hr/documents/")) {
    return "Tài liệu nhân sự"
  }
  if (pathname === "/hr/guide" || pathname.startsWith("/hr/guide/")) {
    return "Hướng dẫn sử dụng"
  }
  return "Tổng quan nhân sự"
}

function HrRouteLabel() {
  const pathname = usePathname()
  return <>{getHrRouteTitle(pathname)}</>
}

export function HrHeaderUser({
  user = DEFAULT_HR_DEMO_USER,
}: {
  user?: HrUserProfile
}) {
  const { openWidget } = useHrChatbot()

  return (
    <header className="sticky top-0 z-20 flex h-15 shrink-0 items-center justify-between gap-4 border-b bg-card/90 px-4 backdrop-blur-md sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <SidebarTrigger
          aria-label="Mở hoặc thu gọn thanh điều hướng HR"
          title="Mở hoặc thu gọn thanh điều hướng HR"
        />
        <span aria-hidden="true" className="h-4 w-px bg-border" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-tight text-foreground">
            <Suspense fallback="Cổng thông tin nhân sự">
              <HrRouteLabel />
            </Suspense>
          </p>
          <p className="hidden truncate text-xs text-muted-foreground sm:block">
            Cổng thông tin nhân sự nội bộ
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-2.5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1.5 border-primary/25 bg-accent/60 text-accent-foreground transition-colors hover:bg-accent active:scale-[0.99]"
          onClick={() => openWidget()}
        >
          <MessageSquareText className="size-3.5 text-primary" aria-hidden="true" />
          <span className="hidden sm:inline">Hỏi Trợ lý HR</span>
        </Button>

        <Button
          nativeButton={false}
          size="sm"
          variant="ghost"
          className="hidden h-8 gap-1 text-muted-foreground hover:text-foreground sm:inline-flex"
          render={<Link href="/chat" />}
        >
          <span>RAG Workspace</span>
          <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </Button>

        <div
          className="flex items-center gap-2 rounded-full border bg-card py-1 pr-2.5 pl-1 shadow-2xs"
          title="Hồ sơ minh họa cho chế độ HR Demo"
        >
          <Avatar size="sm">
            <AvatarFallback className="bg-primary text-[11px] font-medium text-primary-foreground">
              {user.avatarInitials}
            </AvatarFallback>
          </Avatar>
          <div className="hidden min-w-0 text-left leading-tight md:block">
            <p className="truncate text-xs font-medium text-foreground">{user.name}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {user.department}
            </p>
          </div>
          {user.isDemoProfile && (
            <Badge variant="secondary" className="hidden h-5 px-1.5 text-[10px] font-medium lg:inline-flex">
              Demo
            </Badge>
          )}
        </div>
      </div>
    </header>
  )
}
