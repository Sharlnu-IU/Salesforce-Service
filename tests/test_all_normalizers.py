import sys
import os
sys.path.insert(0, os.path.abspath("."))
import shutil
import pandas as pd
from app.services.normalization.service import NormalizationService


def test_all_normalizers():
    temp_dir = "test_normalizers_temp"
    os.makedirs(temp_dir, exist_ok=True)
    norm_service = NormalizationService(output_dir=os.path.join(temp_dir, "output"))

    print("Testing all 8 normalizers...")

    # 1. Account
    account_df = pd.DataFrame([{
        "Id": "001xx000003DHP0AAO",
        "Name": "Acme Corp",
        "Type": "Customer - Direct",
        "Industry": "Technology",
        "AnnualRevenue": 1000000.0,
        "BillingCity": "San Francisco",
        "BillingState": "CA",
        "BillingStreet": "123 Market St",
        "BillingPostalCode": "94105",
        "BillingCountry": "USA",
        "ShippingCity": "Oakland",
        "ShippingState": "CA",
        "ShippingStreet": "456 Broadway",
        "ShippingPostalCode": "94607",
        "ShippingCountry": "USA",
        "OwnerId": "005xx000001SvOmAAK"
    }])
    acc_csv = os.path.join(temp_dir, "account.csv")
    account_df.to_csv(acc_csv, index=False)
    acc_files, acc_stats = norm_service.normalize_csv("Account", acc_csv)
    assert "accounts" in acc_stats and acc_stats["accounts"] == 1
    assert "account_addresses" in acc_stats and acc_stats["account_addresses"] == 2
    assert "account_teams" in acc_stats and acc_stats["account_teams"] == 1
    print("  [PASS] AccountNormalizer")

    # 2. Contact
    contact_df = pd.DataFrame([{
        "Id": "003xx000004TMI1AAO",
        "AccountId": "001xx000003DHP0AAO",
        "FirstName": "Jane",
        "LastName": "Doe",
        "Email": "jane.doe@acme.com",
        "Phone": "555-0100",
        "Title": "VP Engineering",
        "Department": "R&D"
    }])
    con_csv = os.path.join(temp_dir, "contact.csv")
    contact_df.to_csv(con_csv, index=False)
    con_files, con_stats = norm_service.normalize_csv("Contact", con_csv)
    assert con_stats["contacts"] == 1
    assert con_stats["contact_roles"] == 1
    print("  [PASS] ContactNormalizer")

    # 3. Opportunity
    opp_df = pd.DataFrame([{
        "Id": "006xx000001XYZ0AAO",
        "AccountId": "001xx000003DHP0AAO",
        "Name": "Acme - 1000 Licenses",
        "StageName": "Closed Won",
        "Amount": 50000.0,
        "CloseDate": "2026-09-30",
        "Probability": 100.0,
        "ContactId": "003xx000004TMI1AAO"
    }])
    opp_csv = os.path.join(temp_dir, "opportunity.csv")
    opp_df.to_csv(opp_csv, index=False)
    opp_files, opp_stats = norm_service.normalize_csv("Opportunity", opp_csv)
    assert opp_stats["opportunities"] == 1
    assert opp_stats["opportunity_contact_roles"] == 1
    print("  [PASS] OpportunityNormalizer")

    # 4. Lead
    lead_df = pd.DataFrame([{
        "Id": "00Qxx000000ABC1AAO",
        "FirstName": "Bob",
        "LastName": "Smith",
        "Company": "Initech",
        "Email": "bob@initech.com",
        "Status": "Open - Not Contacted",
        "LeadSource": "Web"
    }])
    lead_csv = os.path.join(temp_dir, "lead.csv")
    lead_df.to_csv(lead_csv, index=False)
    lead_files, lead_stats = norm_service.normalize_csv("Lead", lead_csv)
    assert lead_stats["leads"] == 1
    print("  [PASS] LeadNormalizer")

    # 5. Case
    case_df = pd.DataFrame([{
        "Id": "500xx000000DEF1AAO",
        "AccountId": "001xx000003DHP0AAO",
        "ContactId": "003xx000004TMI1AAO",
        "CaseNumber": "00001001",
        "Subject": "Cannot log in",
        "Status": "New",
        "Priority": "High",
        "Description": "User receives 403 error upon sign in"
    }])
    case_csv = os.path.join(temp_dir, "case.csv")
    case_df.to_csv(case_csv, index=False)
    case_files, case_stats = norm_service.normalize_csv("Case", case_csv)
    assert case_stats["cases"] == 1
    assert case_stats["case_comments"] == 1
    print("  [PASS] CaseNormalizer")

    # 6. Task / Event
    task_df = pd.DataFrame([{
        "Id": "00Txx000000GHI1AAO",
        "WhoId": "003xx000004TMI1AAO",
        "WhatId": "006xx000001XYZ0AAO",
        "Subject": "Follow up call",
        "Status": "In Progress",
        "Priority": "Normal",
        "ActivityDate": "2026-09-20"
    }])
    task_csv = os.path.join(temp_dir, "task.csv")
    task_df.to_csv(task_csv, index=False)
    task_files, task_stats = norm_service.normalize_csv("Task", task_csv)
    assert task_stats["tasks"] == 1
    print("  [PASS] TaskEventNormalizer (Task)")

    event_df = pd.DataFrame([{
        "Id": "00Uxx000000JKL1AAO",
        "WhoId": "003xx000004TMI1AAO",
        "WhatId": "001xx000003DHP0AAO",
        "Subject": "Quarterly Review Meeting",
        "StartDateTime": "2026-09-25T14:00:00Z",
        "EndDateTime": "2026-09-25T15:00:00Z",
        "Description": "Review roadmap and renewal"
    }])
    event_csv = os.path.join(temp_dir, "event.csv")
    event_df.to_csv(event_csv, index=False)
    event_files, event_stats = norm_service.normalize_csv("Event", event_csv)
    assert event_stats["events"] == 1
    print("  [PASS] TaskEventNormalizer (Event)")

    # 7. Campaign
    camp_df = pd.DataFrame([{
        "Id": "701xx000000MNO1AAO",
        "Name": "Q3 Enterprise Webinar",
        "Status": "In Progress",
        "StartDate": "2026-07-01",
        "EndDate": "2026-09-30",
        "ExpectedRevenue": 250000.0,
        "LeadId": "00Qxx000000ABC1AAO"
    }])
    camp_csv = os.path.join(temp_dir, "campaign.csv")
    camp_df.to_csv(camp_csv, index=False)
    camp_files, camp_stats = norm_service.normalize_csv("Campaign", camp_csv)
    assert camp_stats["campaigns"] == 1
    assert camp_stats["campaign_members"] == 1
    print("  [PASS] CampaignNormalizer")

    # 8. User
    user_df = pd.DataFrame([{
        "Id": "005xx000001SvOmAAK",
        "Username": "admin@acme.com",
        "LastName": "Admin",
        "FirstName": "Super",
        "Email": "admin@acme.com",
        "IsActive": True,
        "Department": "IT",
        "Title": "System Administrator"
    }])
    user_csv = os.path.join(temp_dir, "user.csv")
    user_df.to_csv(user_csv, index=False)
    user_files, user_stats = norm_service.normalize_csv("User", user_csv)
    assert user_stats["users"] == 1
    print("  [PASS] UserNormalizer")

    # Verify Parquet files are valid readable Parquet
    for f in acc_files + con_files + opp_files + camp_files:
        df = pd.read_parquet(f)
        assert isinstance(df, pd.DataFrame)


    print("  [PASS] Parquet verification across generated files")
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\nALL 8 NORMALIZERS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    test_all_normalizers()
