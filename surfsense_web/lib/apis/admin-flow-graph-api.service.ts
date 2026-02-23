import { flowGraphResponse } from "@/contracts/types/admin-flow-graph.types";
import { baseApiService } from "@/lib/apis/base-api.service";

class AdminFlowGraphApiService {
	getFlowGraph = async () => {
		return baseApiService.get(
			`/api/v1/admin/flow-graph`,
			flowGraphResponse
		);
	};
}

export const adminFlowGraphApiService = new AdminFlowGraphApiService();
