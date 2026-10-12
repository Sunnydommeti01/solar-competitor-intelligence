"""Configuration for the PM Surya Ghar competitor intelligence project.

Districts must be verified against the portal before enabling full extraction.
No API tokens or encrypted payloads belong in this file.
"""

API_URL = (
    "https://pmsuryaghar.gov.in/authenticate/api/verifyAccess/website/"
    "api/registeredVendor/getVendorByStateDistrict"
)

# Used by the original Streamlit UI.
STATES = ("Andhra Pradesh", "Telangana")

# Start with the district confirmed in the portal capture.
# Add districts ONLY after confirming the portal's accepted names/IDs.
DISTRICTS_BY_STATE = {
    "Andhra Pradesh": ["Eluru"],
    "Telangana": [],
}

# Aliases for convenient imports in future scripts.
DISTRICTS = DISTRICTS_BY_STATE
