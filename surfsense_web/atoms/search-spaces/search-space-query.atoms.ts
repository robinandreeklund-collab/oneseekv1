import { atom } from "jotai";
import { atomWithQuery } from "jotai-tanstack-query";
import type { GetSearchSpacesRequest } from "@/contracts/types/search-space.types";
import { searchSpacesApiService } from "@/lib/apis/search-spaces-api.service";
import { getBearerToken } from "@/lib/auth-utils";
import { cacheKeys } from "@/lib/query-client/cache-keys";

export const activeSearchSpaceIdAtom = atom<string | null>(null);

export const searchSpacesQueryParamsAtom = atom<GetSearchSpacesRequest["queryParams"]>({
	skip: 0,
	limit: 10,
	owned_only: false,
});

export const searchSpacesAtom = atomWithQuery((get) => {
	const queryParams = get(searchSpacesQueryParamsAtom);
	const hasToken = !!getBearerToken();

	return {
		queryKey: cacheKeys.searchSpaces.withQueryParams(queryParams),
		enabled: hasToken,
		staleTime: 5 * 60 * 1000,
		queryFn: async () => {
			return searchSpacesApiService.getSearchSpaces({
				queryParams,
			});
		},
	};
});
