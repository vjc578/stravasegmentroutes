#!/usr/bin/env python3.8

import argparse
import subprocess

def download_segment_latlngs(access_token, segment_id):
  completed = subprocess.run(["curl", "-G", "https://www.strava.com/api/v3/segments/{}".format(segment_id), "-H", "Authorization: Bearer {}".format(access_token)], capture_output=True)
  segment_json = completed.stdout.decode("utf-8")
  with open("segment_information/{}.json".format(segment_id), 'w') as file:
      file.write(segment_json)

def main():
    parser = argparse.ArgumentParser(
        description="Determines a route from a selection of Strava segments"
    )
    parser.add_argument("--strava_access_token", type=str, required=True)
    parser.add_argument("--segments", type=str, required=True)

    args = parser.parse_args()
    segments = args.segments.split(',')

    for segment in segments:
        download_segment_latlngs(args.strava_access_token, segment)


if __name__ == "__main__":
    main()
