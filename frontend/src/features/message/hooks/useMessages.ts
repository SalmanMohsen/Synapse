import { useMutation, useQuery, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import { messageApi } from '../api/messageApi'
import type { MessageCreate, MessageRead, MessageUpdate } from '../types/message.types'
import { toast } from '@/shared/hooks/useToast'

// ── List (infinite, cursor-based — oldest first display) ──────────────────────
// Pages are fetched in reverse: the first fetch gets the latest 50 messages.
// "Load earlier" fetches the next page using the cursor (before_id).
// Items are displayed oldest-first by reversing each page.

export const useMessages = (ticketId: string) =>
  useInfiniteQuery({
    queryKey: ['messages', ticketId],
    queryFn: ({ pageParam }) =>
      messageApi.list(ticketId, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? (lastPage.next_cursor ?? undefined) : undefined,
    enabled: !!ticketId,
  })

// ── Simple single-page query (used by TicketDetailResponse initial load) ──────
// The ticket detail endpoint already returns the first page of messages.
// We prime the infinite query cache from that initial load in TicketDetailPage.

// ── Mutations ─────────────────────────────────────────────────────────────────

export const useSendMessage = (ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: MessageCreate) => messageApi.create(ticketId, data),
    onSuccess: (msg) => {
      // Optimistically append to the first (newest) page
      qc.setQueryData(['messages', ticketId], (old: Parameters<typeof _appendMessage>[1]) =>
        _appendMessage(msg, old)
      )
    },
    onError: () => toast('Failed to send message', 'error'),
  })
}

export const useEditMessage = (ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ messageId, data }: { messageId: string; data: MessageUpdate }) =>
      messageApi.edit(ticketId, messageId, data),
    onSuccess: (updated) => {
      qc.setQueryData(['messages', ticketId], (old: Parameters<typeof _patchMessage>[1]) =>
        _patchMessage(updated, old)
      )
    },
    onError: () => toast('Failed to edit message', 'error'),
  })
}

export const useDeleteMessage = (ticketId: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (messageId: string) => messageApi.delete(ticketId, messageId),
    onSuccess: (updated) => {
      qc.setQueryData(['messages', ticketId], (old: Parameters<typeof _patchMessage>[1]) =>
        _patchMessage(updated, old)
      )
    },
    onError: () => toast('Failed to delete message', 'error'),
  })
}

// ── Cache helpers ─────────────────────────────────────────────────────────────

type InfiniteData = {
  pages: { items: MessageRead[]; has_more: boolean; next_cursor: string | null }[]
  pageParams: unknown[]
}

function _appendMessage(msg: MessageRead, old: InfiniteData | undefined): InfiniteData {
  if (!old) {
    return {
      pages: [{ items: [msg], has_more: false, next_cursor: null }],
      pageParams: [undefined],
    }
  }
  // Append to the FIRST page (which holds the newest messages)
  const [first, ...rest] = old.pages
  return {
    ...old,
    pages: [{ ...first, items: [...first.items, msg] }, ...rest],
  }
}

function _patchMessage(updated: MessageRead, old: InfiniteData | undefined): InfiniteData | undefined {
  if (!old) return old
  return {
    ...old,
    pages: old.pages.map((page) => ({
      ...page,
      items: page.items.map((m) => (m.id === updated.id ? updated : m)),
    })),
  }
}