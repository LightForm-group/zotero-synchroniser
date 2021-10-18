import pickle
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from tqdm import tqdm
from bs4 import BeautifulSoup
from pyzotero import zotero
import yaml
from thefuzz import process
import dateparser


class MatchType(Enum):
    success = 1
    not_found_on_zotero = 2
    not_found_on_website = 3


@dataclass
class Match:
    type: MatchType
    ratio: int
    web_record: Optional[dict]
    zotero_record: Optional[dict]


def main():
    website_records = get_website_records()
    zotero_records = get_zotero_records()
    match_summary = compare_records(website_records, zotero_records)
    print_report(match_summary)


def print_report(results_summary: List[Match]):
    matches = [match for match in results_summary if match.type == MatchType.success]
    zotero_missing = [match for match in results_summary if match.type == MatchType.not_found_on_zotero]
    website_missing = [match for match in results_summary if match.type == MatchType.not_found_on_website]

    with open("results.tsv", "w", encoding="utf-8") as output_file:
        output_file.write(f"{len(matches)} records match on website and Zotero.\n")
        output_file.write(f"{len(zotero_missing)} records on website not found on Zotero.\n")
        output_file.write(f"{len(website_missing)} records on Zotero not found on Website\n")
        output_file.write("Successful matches:\nWebsite title\tZotero title\tSuccess\tRatio\n")
        for match in results_summary:
            if match.type == MatchType.success:
                output_file.write(f"{match.web_record['title']}\t{match.zotero_record['title']}"
                                  f"\t{match.type.name}\t{match.ratio}\n")
        output_file.write("Records on website not found on Zotero:\nWebsite title\n")
        for match in results_summary:
            if match.type == MatchType.not_found_on_zotero:
                output_file.write(f"{match.web_record['title']}\n")
        output_file.write("Records on Zotero not found on Website:\nZotero title\tauthors\turl\tdate\n")
        for match in results_summary:
            if match.type == MatchType.not_found_on_website:
                authors = ""
                for author in match.zotero_record["authors"]:
                    if author["creatorType"] == "author":
                        authors += f'{author["firstName"][0]}.{author["lastName"]}, '
                authors = authors[:-2]
                output_file.write(f"{match.zotero_record['title']}\t{authors}\t{match.zotero_record['url']}\t"
                                  f"{match.zotero_record['date'].strftime('%Y/%m/%d')}\n")


def compare_records(website_records: List[dict], zotero_records: List[dict], match_threshold: int = 90):
    summary = []
    zotero_titles = [record["title"] for record in zotero_records]
    for web_record in tqdm(website_records):
        ratios = process.extract(web_record["title"], zotero_titles)
        ratios = {value: key for key, value in ratios}
        max_closeness = max(list(ratios.keys()))
        if max_closeness > match_threshold:
            match_title = ratios[max_closeness]
            summary.append(Match(MatchType.success, max_closeness, web_record, get_record_by_title(zotero_records,
                                                                                                   match_title)))
            zotero_titles.remove(ratios[max_closeness])
        else:
            summary.append(Match(MatchType.not_found_on_zotero, max_closeness, web_record, None))
    for title in zotero_titles:
        summary.append(Match(MatchType.not_found_on_website, 0, None, get_record_by_title(zotero_records, title)))
    return summary


def get_website_records() -> List[dict]:
    records = []
    page = urllib.request.urlopen('https://lightform.org.uk/publications')
    soup = BeautifulSoup(page.read(), 'html.parser')
    li_tags = soup.find_all('li')
    for tag in li_tags:
        if "class" in tag.attrs:
            if "publication-tile" in tag["class"]:
                records.append({"title": tag.h3.text, "authors": tag.p.text})
    return records


def get_zotero_records() -> List[dict]:
    records = []
    settings = get_settings()
    zot = zotero.Zotero(settings["lightform_group_id"], "group", settings["api_key"])
    results = zot.everything(zot.top())
    for record in results:
        if "DOI" in record["data"]:
            url = f'https://{record["data"]["DOI"]}'
        else:
            url = record["data"]["url"]
        records.append({"title": record["data"]["title"],
                        "authors": record["data"]["creators"],
                        "date": dateparser.parse(record["data"]["date"]),
                        "url": url})
    return records

def get_settings() -> dict:
    with open("settings.yaml") as input_file:
        return yaml.safe_load(input_file)


def get_record_by_title(records: List[dict], title: str) -> Optional[dict]:
    for record in records:
        if record["title"] == title:
            return record
    return None


if __name__ == '__main__':
    main()
