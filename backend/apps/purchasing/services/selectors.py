"""Read-only purchasing contract used by the project financial view."""


def project_costs(project):
    # Include the owning acquisition, capitalization correction, depreciation,
    # fulfillment and return sources. Posted journals remain the only valuation.
    from apps.reporting.attribution import project_costs as posted_costs

    return posted_costs(project)
