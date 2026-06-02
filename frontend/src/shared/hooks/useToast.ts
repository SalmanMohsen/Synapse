import { useState, useCallback, useRef } from 'react'

export type ToastVariant = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  message: string
  variant: ToastVariant
}

let toastFn: ((message: string, variant?: ToastVariant) => void) | null = null

// Allow imperative toast calls from outside React (e.g. query callbacks)
export function toast(message: string, variant: ToastVariant = 'info') {
  toastFn?.(message, variant)
}

export function useToastStore() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timerMap = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const push = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((prev) => [...prev, { id, message, variant }])
    const t = setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id))
      timerMap.current.delete(id)
    }, 3800)
    timerMap.current.set(id, t)
  }, [])

  const dismiss = useCallback((id: string) => {
    const t = timerMap.current.get(id)
    if (t) { clearTimeout(t); timerMap.current.delete(id) }
    setToasts((prev) => prev.filter((x) => x.id !== id))
  }, [])

  // Register globally so `toast()` can be used outside React
  toastFn = push

  return { toasts, push, dismiss }
}

export function useToast() {
  // Components call this to get a push function
  return { toast: toastFn ?? (() => {}) }
}