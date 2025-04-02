import arxiv
import datetime
from collections import defaultdict

def count_submissions_in_category(category, start_date, end_date, days):
    """
    Returns a dictionary mapping date -> submission_count for the given category 
    between start_date and end_date.
    """
    day_counts = defaultdict(int)
    
    # Create a client to handle queries
    client = arxiv.Client(
        page_size=2000,     # max items per query page
        delay_seconds=3,    # polite delay between requests
        num_retries=3       # number of retries for transient errors
    )
    
    delta = datetime.timedelta(days=days)
    current_start = start_date
    
    while current_start <= end_date:
        current_end = current_start + delta  # 1-day slice

        # Format dates in YYYYMMDDHHMM (arXiv uses yyyymmddhhmm in queries)
        date_str_start = current_start.strftime('%Y%m%d0000')
        date_str_end   = current_end.strftime('%Y%m%d0000')
        
        # Build the search query for the single-day range
        search = arxiv.Search(
            query=f"cat:{category} AND submittedDate:[{date_str_start} TO {date_str_end}]",
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Ascending
        )
        
        # Use client.results(search) rather than search.results() to avoid the deprecation warning
        results = list(client.results(search))
        day_counts[current_start] = len(results)
        
        current_start = current_end
    
    return day_counts

def average_daily_submissions(category, days=120):
    """
    Fetch data for the specified category over the past 'days' days,
    then compute average daily submissions.
    """
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    
    day_counts = count_submissions_in_category(category, start_date, end_date, days=days)
    total_submissions = sum(day_counts.values())
    # Just use the exact number of full days in the dictionary for average
    avg_per_day = total_submissions / len(day_counts) if day_counts else 0
    return total_submissions


avg_csAI = average_daily_submissions("cs.AI", days=5)
avg_csLG = average_daily_submissions("cs.LG", days=5)

print(f"Total submissions for cs.AI over last 5 days: {avg_csAI:.2f}")
print(f"Total submissions for cs.LG over last 5 days: {avg_csLG:.2f}")