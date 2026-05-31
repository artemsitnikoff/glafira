import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { client } from '../client'
import type {
  CandidateGridItem,
  ApplicationHistoryItem,
  AssignToVacancyRequest,
  ApplicationRow,
  CandidateDetail,
  Paginated
} from '../aliases'

export interface CandidateFilters {
  search?: string
  city?: string
  exp?: number
  score_min?: number
  score_max?: number
  source?: string
  vacancy_id?: string
  stage?: string
  tags?: string[]
  added_period?: string
  sort?: string
  order?: string
}

/**
 * Infinite query for candidates list
 */
export function useCandidates(filters: CandidateFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['candidates', filters],
    queryFn: async ({ pageParam = 1 }) => {
      const params = new URLSearchParams()
      params.set('page', String(pageParam))
      params.set('page_size', '24')

      // Add non-empty filter values
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          if (Array.isArray(value)) {
            if (value.length > 0) {
              params.set(key, value.join(','))
            }
          } else {
            params.set(key, String(value))
          }
        }
      })

      const response = await client.get(`/candidates?${params}`)
      return response.data as Paginated<CandidateGridItem>
    },
    getNextPageParam: (lastPage, allPages) => {
      // Бэк отдаёт `pages` (всего страниц), а НЕ `has_next`. Следующая страница есть,
      // пока загруженных страниц меньше общего числа.
      return allPages.length < lastPage.pages ? allPages.length + 1 : undefined
    },
    initialPageParam: 1
  })
}

/**
 * Get single candidate details
 */
export function useCandidate(candidateId: string) {
  return useQuery({
    queryKey: ['candidates', candidateId],
    queryFn: async () => {
      const response = await client.get(`/candidates/${candidateId}`)
      return response.data as CandidateDetail
    },
    enabled: !!candidateId
  })
}

/**
 * Get candidate applications history
 */
export function useCandidateApplications(candidateId: string) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'applications'],
    queryFn: async () => {
      const response = await client.get(`/candidates/${candidateId}/applications`)
      return response.data as ApplicationHistoryItem[]
    },
    enabled: !!candidateId
  })
}

/**
 * Assign candidate to vacancy mutation
 */
export function useAssignToVacancy() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  return useMutation({
    mutationFn: async ({ candidateId, data }: {
      candidateId: string
      data: AssignToVacancyRequest
    }) => {
      const response = await client.post(
        `/candidates/${candidateId}/applications`,
        data
      )
      return response.data as ApplicationRow
    },
    onSuccess: (_, variables) => {
      // Invalidate relevant queries
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      queryClient.invalidateQueries({
        queryKey: ['candidates', variables.candidateId, 'applications']
      })
      queryClient.invalidateQueries({
        queryKey: ['vacancies', variables.data.vacancy_id, 'candidates']
      })

      // Navigate to funnel view - using data from request since ApplicationRow doesn't have vacancy_id
      navigate(`/vacancies/${variables.data.vacancy_id}/candidates/${variables.candidateId}`)
    }
  })
}