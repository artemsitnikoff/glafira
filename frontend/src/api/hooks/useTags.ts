import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { components } from '@/api/types'

type TagOut = components['schemas']['TagOut']

export function useTags() {
  return useQuery({
    queryKey: ['tags'],
    queryFn: async () => {
      const response = await api.get('/settings/tags')
      return response.data as TagOut[]
    },
  })
}