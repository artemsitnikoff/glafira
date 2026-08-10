import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

// Локальный тип (openapi не регенерён)
export interface MessageTemplateOut {
  id: string
  company_id: string
  name: string
  body: string
  order_index: number
  created_at: string
  updated_at: string
}

// enabled=true по умолчанию → существующие вызовы без аргумента не меняются.
// Попап чатов не рисует шаблоны (showTemplates=false) → лишний запрос не идёт.
export function useMessageTemplates(enabled = true) {
  return useQuery({
    queryKey: ['message-templates'],
    queryFn: async () => {
      const response = await api.get('/message-templates')
      return response.data as MessageTemplateOut[]
    },
    enabled,
  })
}