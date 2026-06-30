import pyoxigraph
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from datetime import datetime

less_than_relation = pyoxigraph.NamedNode("https://w3id.org/tree#LessThanRelation")
greater_than_relation = pyoxigraph.NamedNode("https://w3id.org/tree#GreaterThanRelation")
tree_node = pyoxigraph.NamedNode("https://w3id.org/tree#node")
tree_member = pyoxigraph.NamedNode("https://w3id.org/tree#member")
tss_snippet = pyoxigraph.NamedNode("https://w3id.org/tss#snippet")

years_set = set()
months_set = set()
day_set = set()
members_set = set()

objects_store = pyoxigraph.Store(path="objects_store")


def fetch_ldes_year(base_url, before_date, after_date):
    response = requests.get(base_url)
    if response.status_code == 200:
        year_store = pyoxigraph.Store()
        year_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
        print(f"Loaded {len(year_store)} triples from {base_url}")
        for s, p, o, g in year_store.quads_for_pattern(None, tree_node, None, None):
            url_string = o.value
            match = re.search(r'(\d{4})\.trig$', url_string) 
            if match:
                actual_year = int(match.group(1))
                # Allow the year folder if it falls within our boundary years (inclusive)
                if after_date.year <= actual_year <= before_date.year:
                    years_set.add(o)
        print(f"Years found: {years_set}")

def fetch_ldes_month(before_date, after_date):
    for year_uri in years_set:
        response = requests.get(year_uri.value)
        if response.status_code == 200:
            year_store = pyoxigraph.Store()
            year_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            for s, p, o, g in year_store.quads_for_pattern(None, tree_node, None, None):
                url_string = o.value
                match = re.search(r'/(\d{4})/(\d{2})/', url_string)
                if match:
                    actual_year = int(match.group(1))
                    actual_month = int(match.group(2))
                    
                    # Create year/month tuples for a flawless range comparison
                    after_tuple = (after_date.year, after_date.month)
                    before_tuple = (before_date.year, before_date.month)
                    current_tuple = (actual_year, actual_month)
                    
                    # Python natively handles tuple comparison chronologically:
                    # (2025, 1) <= (2025, 9) <= (2026, 1) -> True
                    if after_tuple <= current_tuple <= before_tuple:
                        months_set.add(o)
    print(f"Months found: {months_set}")

def fetch_ldes_day():
    for month_uri in months_set:
        response = requests.get(month_uri.value)
        if response.status_code == 200:
            month_store = pyoxigraph.Store()
            month_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            for s, p, o,g in month_store.quads_for_pattern(None, tree_node, None, None):
                day_set.add(o)
    print(f"Days found: {day_set}")

def fetch_ldes_members():
    for day_uri in day_set:
        response = requests.get(day_uri.value)
        if response.status_code == 200:
            day_store = pyoxigraph.Store()
            day_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            
            # 1. Search for 'tree_member' as the predicate
            for s, p, member_uri, g in day_store.quads_for_pattern(None, tree_member, None, None):
                # 2. Add the OBJECT (member_uri), not the subject
                members_set.add(member_uri)
                print(f"Member found: {member_uri}")
                
            # 3. Fetch quads for each member found
            for subject in members_set:
                for s, p, o, g in day_store.quads_for_pattern(subject, None, None, None):
                    quad = pyoxigraph.Quad(s, p, o, pyoxigraph.DefaultGraph())
                    objects_store.add(quad)
                    print(f"Quad added: {quad}")

                #print(f"Object: {o}")
                
            

def main():
    before_date = '01-01-2026'
    after_date = '01-03-2025'

    parsed_before_date = datetime.strptime(before_date, '%d-%m-%Y')
    parsed_after_date = datetime.strptime(after_date, '%d-%m-%Y')



    fetch_ldes_year("https://shehabeldeenayman.github.io/Gent-Terneuzen-canal/conductivity/conductivity.trig", before_date=parsed_before_date, after_date=parsed_after_date) 
    print("/-------------------------------------------------/")
    fetch_ldes_month(before_date=parsed_before_date, after_date=parsed_after_date)
    print("/-------------------------------------------------/")
    #fetch_ldes_day()
    print("/-------------------------------------------------/")
    #fetch_ldes_members()
    print("/-------------------------------------------------/")




if __name__=="__main__":
    main()