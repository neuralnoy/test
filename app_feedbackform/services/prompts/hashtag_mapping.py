"""
Hashtag mapping for the feedback form application.
This is a temporary generic mapping and will be replaced with actual business logic later.
"""

MAPPING_TABLE = [
    {
        "id": "P01",
        "typeName": "Product",
        "typeValue": "CREDIT_CARD",
        "relatedTo": "Calls",
        "description": "Problem with credit card"
    },
    {
        "id": "C01",
        "typeName": "Category",
        "typeValue": "CARDS",
        "relatedTo": "Calls",
        "description": "Problem with cards" 
    },
    {
        "id": "T01",
        "typeName": "Topic",
        "typeValue": "CREDIT_CARD_LOST_OR_STOLEN",
        "relatedTo": "Calls",
        "description": "User lost or had their credit card stolen"
    },
    {
        "id": "S01",
        "typeName": "Subtopic",
        "typeValue": "American Express",
        "relatedTo": "Calls",
        "description": "Users complain is related to American Express" 
    },
    {
        "id": "H01",
        "typeName": "Hashtag",
        "typeValue": "#CreditCardIssue",
        "relatedTo": "Calls",
        "description": "Problem with credit card" 
    },
    {
        "id": "P02",
        "typeName": "Product",
        "typeValue": "LOAN",
        "relatedTo": "Calls",
        "description": "User has a problem with their credit card"
    },
    {
        "id": "C02",
        "typeName": "Category",
        "typeValue": "LOANS",
        "relatedTo": "Calls",
        "description": "Problem with cards" 
    },
    {
        "id": "T02",
        "typeName": "Topic",
        "typeValue": "LOAN_REPAYMENT",
        "relatedTo": "Calls",
        "description": "Problem with loan"
    },
    {
        "id": "S02",
        "typeName": "Subtopic",
        "typeValue": "Mortgage",
        "relatedTo": "Calls",
        "description": "Problem with mortgage" 
    },
    {
        "id": "H02",
        "typeName": "Hashtag",
        "typeValue": "#MortgageIssue",
        "relatedTo": "Calls",
        "description": "Problem with mortgage" 
    },
    {
        "id": "P03",
        "typeName": "Product",
        "typeValue": "MORTGAGE",
        "relatedTo": "Calls",
        "description": "Problem with mortgage" 
    },
    {
        "id": "C03",
        "typeName": "Category",
        "typeValue": "MORTGAGES",
        "relatedTo": "Calls",
        "description": "Problem with mortgages" 
    },
    {
        "id": "T03",
        "typeName": "Topic",
        "typeValue": "MORTGAGE_REPAYMENT",
        "relatedTo": "Calls",
        "description": "Problem with mortgages" 
    },
    {
        "id": "S03",
        "typeName": "Subtopic",
        "typeValue": "Mortgage",
        "relatedTo": "Calls",
        "description": "Problem with mortgages" 
    },
    {
        "id": "H03",
        "typeName": "Hashtag",
        "typeValue": "#MortgageIssue",
        "relatedTo": "Calls",
        "description": "Problem with mortgages" 
    },
    {
        "id": "C04",
        "typeName": "Category",
        "typeValue": "CARDS",
        "relatedTo": "Forms",
        "description": "Problem with cards" 
    },
    {
        "id": "H04",
        "typeName": "Hashtag",
        "typeValue": "#CreditCardIssue",
        "relatedTo": "Forms",
        "description": "Problem with credit card" 
    },
    {
        "id": "C05",
        "typeName": "Category",
        "typeValue": "LOANS",
        "relatedTo": "Forms",
        "description": "Problem with cards" 
    },
    {
        "id": "H05",
        "typeName": "Hashtag",
        "typeValue": "#MortgageIssue",
        "relatedTo": "Forms",
        "description": "Problem with mortgage" 
    },
    {
        "id": "C06",
        "typeName": "Category",
        "typeValue": "MORTGAGES",
        "relatedTo": "Forms",
        "description": "Problem with mortgages" 
    },
    {
        "id": "H04",
        "typeName": "Hashtag",
        "typeValue": "#CreditCardIssue",
        "relatedTo": "Forms",
        "description": "Problem with credit card" 
    }
]

def get_hashtag_mapping():
    """
    Get the reason mapping dictionary.
    
    Returns:
        dict: The reason mapping dictionary
    """
    return MAPPING_TABLE 