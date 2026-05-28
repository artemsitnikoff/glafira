import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { components } from '@/api/types'

type Paginated = components['schemas']['Paginated_VacancyDetail_']

export interface UseVacanciesParams {
  page?: number
  page_size?: number
  status?: string | null
  search?: string | null
  sort?: string | null
  order?: string
}

export function useVacancies(params: UseVacanciesParams = {}) {
  const {
    page = 1,
    page_size = 50,
    status = 'active',
    search = null,
    sort = null,
    order = 'asc'
  } = params

  const searchParams = new URLSearchParams()
  searchParams.append('page', page.toString())
  searchParams.append('page_size', page_size.toString())
  if (status) searchParams.append('status', status)
  if (search) searchParams.append('search', search)
  if (sort) searchParams.append('sort', sort)
  searchParams.append('order', order)

  return useQuery({
    queryKey: ['vacancies', { page, page_size, status, search, sort, order }],
    queryFn: async () => {
      const response = await api.get(`/vacancies?${searchParams.toString()}`)
      return response.data as Paginated
    },
  })
}