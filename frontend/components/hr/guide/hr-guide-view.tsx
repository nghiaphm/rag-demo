"use client"

import Link from "next/link"
import { useEffect } from "react"
import { BookOpen, CheckCircle2, MessageSquareText, Sparkles } from "lucide-react"

import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
    <section aria-labelledby="hr-guide-title" className="mx-auto w-full max-w-6xl space-y-8">
      <div className="flex flex-col gap-5 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl space-y-2">
          <h1
            id="hr-guide-title"
            className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl"
          >
            Hướng dẫn sử dụng HR Portal
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Cách khai thác bảng tổng quan nhân sự, tra cứu tài liệu nội bộ và hỏi đáp với Trợ lý RAG có đối chiếu nguồn.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            className="gap-1.5 transition-transform active:scale-[0.99]"
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

      <div className="grid gap-5 md:grid-cols-2">
        {HR_GUIDE_SECTIONS.map((section) => (
          <article
            key={section.id}
            className="flex h-full flex-col justify-between rounded-xl border bg-card p-6"
          >
            <div className="space-y-4">
              <div className="space-y-1.5 border-b pb-4">
                <h2 className="text-base font-semibold tracking-tight text-foreground">
                  {section.title}
                </h2>
                <p className="max-w-prose text-xs leading-5 text-muted-foreground">
                  {section.summary}
                </p>
              </div>
              <ul className="space-y-3 text-sm leading-6 text-muted-foreground">
                {section.steps.map((step, index) => (
                  <li key={index} className="flex items-start gap-2.5">
                    <CheckCircle2 className="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </div>

      <section aria-labelledby="hr-prompts-heading" className="rounded-xl border bg-card p-6">
        <div className="space-y-1.5 pb-5">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            <h2 id="hr-prompts-heading" className="text-base font-semibold tracking-tight">
              Câu hỏi mẫu để thử nhanh với Trợ lý HR
            </h2>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Nhấp vào một tình huống dưới đây để mở ngay khung Chatbot với câu hỏi được điền sẵn.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HR_PROMPT_TEMPLATES.map((template) => (
            <div
              key={template.id}
              className="flex flex-col justify-between gap-4 rounded-xl border bg-muted/25 p-4 transition-all duration-150 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card hover:shadow-xs"
            >
              <div className="space-y-2">
                <Badge variant="outline" className="bg-background text-[11px] font-medium">
                  {getHrCategoryLabel(template.category)}
                </Badge>
                <p className="text-sm font-semibold text-foreground">{template.title}</p>
                <p className="text-xs leading-5 text-muted-foreground">{template.prompt}</p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="w-full gap-1.5 bg-background hover:bg-accent hover:text-accent-foreground"
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
                <MessageSquareText className="size-3.5 text-primary" aria-hidden="true" />
                <span>Thử câu hỏi này</span>
              </Button>
            </div>
          ))}
        </div>
      </section>
    </section>
  )
}
