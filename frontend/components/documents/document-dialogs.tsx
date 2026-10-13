"use client"

import { FileUp, Trash2, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

export function UploadDocumentDialog({
  mode = "create",
}: {
  mode?: "create" | "version"
}) {
  const isVersion = mode === "version"

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button variant={isVersion ? "outline" : "default"} size={isVersion ? "sm" : "default"} />
        }
      >
        {isVersion ? <FileUp aria-hidden="true" /> : <Upload aria-hidden="true" />}
        {isVersion ? "Phiên bản mới" : "Thêm tài liệu"}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isVersion ? "Tải lên phiên bản mới" : "Thêm tài liệu"}</DialogTitle>
          <DialogDescription>
            Chọn file PDF, Markdown, TXT hoặc XLSX. Backend xử lý đồng bộ và chưa cung cấp
            tiến trình polling.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <label htmlFor={`document-file-${mode}`} className="text-sm font-medium">
            File tài liệu
          </label>
          <Input
            id={`document-file-${mode}`}
            type="file"
            accept=".pdf,.md,.markdown,.txt,.xlsx"
            aria-describedby={`document-file-help-${mode}`}
          />
          <p id={`document-file-help-${mode}`} className="text-xs leading-5 text-muted-foreground">
            Bản xem trước không đọc hoặc gửi file đã chọn.
          </p>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Đóng</DialogClose>
          <Button disabled>{isVersion ? "Tạo phiên bản" : "Tải lên"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DeleteDocumentDialog({ fileName }: { fileName: string }) {
  return (
    <Dialog>
      <DialogTrigger render={<Button variant="destructive" size="sm" />}>
        <Trash2 aria-hidden="true" />
        Xóa tài liệu
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Xác nhận xóa tài liệu?</DialogTitle>
          <DialogDescription>
            “{fileName}” sẽ bị unpublish và không còn đủ điều kiện retrieval. Backend giữ raw
            files cùng lịch sử audit; việc dọn vector có thể hoàn tất sau.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs leading-5 text-muted-foreground">
          Đây là dialog fixture. Không có request xóa nào được gửi.
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Hủy</DialogClose>
          <Button variant="destructive" disabled>
            Xác nhận xóa
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
