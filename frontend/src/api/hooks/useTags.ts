import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

// Локальный тип (openapi не регенерён): тег + число использований.
export interface TagManage {
  id: string
  name: string
  color: string | null
  usage_count: number
  created_at: string
}

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: async () => {
      const response = await api.get('/settings/tags')
      return response.data as TagManage[]
    },
  })
}
