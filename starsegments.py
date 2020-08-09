import argparse
import sys
import subprocess

def main():
    parser = argparse.ArgumentParser(
        description="Starts a list of strava segments"
    )

    parser.add_argument("--segments", type=str, required=True)
    parser.add_argument("--strava_access_token", type=str, required=True)

    args = parser.parse_args()
    segments = args.segments.split(',')

    for segment in segments:
        completed = subprocess.run(["curl", "-d", "starred='true'", "-X", "PUT", "https://www.strava.com/api/v3/segments/{}/starred".format(segment), "-H", "Authorization: Bearer {}".format(args.strava_access_token)], capture_output=True)
        segment_json = completed.stdout.decode("utf-8")
        print(segment_json)

if __name__ == "__main__":
    main()
