"use client"

import Link from "next/link"
import { useEffect } from "react"
import { BookOpen, CheckCircle2, MessageSquareText, Sparkles } from "lucide-react"

import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { HR_GUIDE_SECTIONS, HR_PROMPT_TEMPLATES } from "@/fixtures/hr-guide"
import { getHrCategoryLabel } from "@/lib/hr/document-categories"

export function HrGuideView() {
  const { openWidget, setPageContext } = useHrChatbot()

  useEffect(() => {
    setPageContext({
      route: "/hr/guide",
      title: "Hướng dẫn sử dụng",
    })
  }, [setPageContext])

  return (
    <section aria-labelledby="hr-guide-title" className="mx-auto w-full max-w-6xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Tài liệu hướng dẫn</p>
          <h1 id="hr-guide-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Hướng dẫn sử dụng HR Portal
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Cách khai thác Dashboard nhân sự, quản lý và xem nội dung tài liệu, cũng như hỏi đáp với Trợ lý RAG có kiểm chứng nguồn.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            className="gap-1.5"
            onClick={() => openWidget({ pageContext: { route: "/hr/guide", title: "Hướng dẫn sử dụng" } })}
          >
            <MessageSquareText className="size-4" aria-hidden="true" />
            <span>Mở Trợ lý HR</span>
          </Button>
          <Button nativeButton={false} variant="outline" render={<Link href="/hr/documents" />}>
            <BookOpen className="size-4" aria-hidden="true" />
            <span>Đi tới Kho tài liệu</span>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {HR_GUIDE_SECTIONS.map((section) => (
          <Card key={section.id} className="h-full">
            <CardHeader>
              <CardTitle className="text-base">{section.title}</CardTitle>
              <CardDescription>{section.summary}</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2.5 text-sm leading-6 text-muted-foreground">
                {section.steps.map((step, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <CheckCircle2 className="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            <CardTitle className="text-base">Câu hỏi mẫu để thử nhanh với Trợ lý HR</CardTitle>
          </div>
          <CardDescription>
            Nhấp vào một tình huống dưới đây để mở ngay khung Chatbot với câu hỏi được điền sẵn.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {HR_PROMPT_TEMPLATES.map((template) => (
              <div
                key={template.id}
                className="flex flex-col justify-between gap-3 rounded-lg border bg-muted/20 p-3.5"
              >
                <div className="space-y-1.5">
                  <Badge variant="outline" className="text-[11px]">
                    {getHrCategoryLabel(template.category)}
                  </Badge>
                  <p className="text-sm font-medium">{template.title}</p>
                  <p className="text-xs leading-5 text-muted-foreground">{template.prompt}</p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-full gap-1.5"
                  onClick={() =>
                    openWidget({
                      pageContext: {
                        route: "/hr/guide",
                        title: "Hướng dẫn sử dụng",
                        selectedCategory: template.category,
                      },
                      prompt: template.prompt,
                    })
                  }
                >
                  <MessageSquareText className="size-3.5" aria-hidden="true" />
                  <span>Thử câu hỏi này</span>
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
