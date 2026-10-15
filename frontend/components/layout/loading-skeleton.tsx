import { Skeleton } from "@/components/ui/skeleton"

export function LoadingSkeleton() {
  return <div aria-hidden="true" className="space-y-4 rounded-xl border p-4">
    {[0, 1, 2].map(index => <div key={index} className="space-y-2">
      <Skeleton className="h-4 w-2/3 motion-reduce:animate-none" />
      <Skeleton className="h-4 w-full motion-reduce:animate-none" />
      <Skeleton className="h-4 w-1/2 motion-reduce:animate-none" />
    </div>)}
  </div>
}
