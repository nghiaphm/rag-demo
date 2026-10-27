"use client"

import { useRef, useState } from "react"
import { FileText, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { DocumentPreview } from "@/components/chat/document-preview"
import type { MessageAttachment } from "@/types/chat"

export function MessageAttachmentChip({ attachment, apiBaseUrl }: { attachment: MessageAttachment; apiBaseUrl: string | null }) {
  const [open, setOpen] = useState(false)
  const closeButton = useRef<HTMLButtonElement>(null)
  return <Sheet open={open} onOpenChange={setOpen}>
    <SheetTrigger render={<Button type="button" variant="outline" className="h-auto max-w-full whitespace-normal bg-background text-foreground" />}
      aria-label={`Xem tệp đính kèm ${attachment.file_name}`}>
      <FileText className="shrink-0" aria-hidden="true" /><span className="min-w-0 break-all">{attachment.file_name}</span>
    </SheetTrigger>
    <SheetContent side="right" showCloseButton={false} initialFocus={closeButton} className="w-full sm:max-w-xl">
      <SheetHeader className="pr-12"><SheetTitle className="break-words">{attachment.file_name}</SheetTitle>
        <SheetDescription>Phiên bản tài liệu đã gắn với tin nhắn. Attachment không thay đổi phạm vi truy xuất của chat.</SheetDescription></SheetHeader>
      <SheetClose render={<Button ref={closeButton} type="button" variant="ghost" size="icon" className="absolute top-3 right-3" aria-label="Đóng xem trước" />}><X aria-hidden="true" /></SheetClose>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">{open && <DocumentPreview reference={attachment} apiBaseUrl={apiBaseUrl} />}</div>
    </SheetContent>
  </Sheet>
}
