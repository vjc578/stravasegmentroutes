#!/usr/bin/env python3.8

import argparse
import sys
import pprint
import subprocess
import json
import math
from os import path

import googlemaps
import segmentdownloader

def write_gpx(latlons, filename):
    with open(filename, 'w') as file:
        file.write(r'<?xml version="1.0" encoding="UTF-8"?>')
        file.write('\n')
        file.write(r'<gpx version="1.0">')
        file.write(r'  <name>Example gpx</name>')
        file.write('\n')
        file.write(r'  <trk><name>Example gpx</name><number>1</number><trkseg>')
        file.write('\n')
        for latlon in latlons:
            file.write('    <trkpt lat="{}" lon="{}"></trkpt>'.format(latlon["lat"], latlon["lng"]))
            file.write('\n')
        file.write('  </trkseg></trk>')
        file.write('\n')
        file.write('</gpx>')

def get_segment_latlngs(strava_access_token, segment_id):
  filename = "segment_information/{}.json".format(segment_id)
  if not path.exists(filename):
      segmentdownloader.download_segment_latlngs(strava_access_token, segment_id)

  with open(filename, "r") as file:
    segment_json = json.loads(file.read())
    segment_polyline = segment_json["map"]["polyline"]
    segment_latlngs = googlemaps.convert.decode_polyline(segment_polyline)
    return segment_latlngs

def get_directions(gmaps, start_latlng, end_latlng):
    directions_result = gmaps.directions(start_latlng, end_latlng, mode="bicycling")
    polyline = directions_result[0]["overview_polyline"]["points"]
    return googlemaps.convert.decode_polyline(polyline)

def get_segment_ordering(gmaps, start_latlng, segment_latlngs, max_segments, indices):
    # This uses the nearest neighbor greedy algorithm for determining
    # the segment ordering. It starts with the origin, then finds the next
    # closest segment, and then the next closest, etc ... This is not optimal.
    # In fact the best known optimal algorithm is exponential in the number of
    # segments. There are better approximate algorithms but I'm not using them here.
    # You are riding your bike, does it really have to be the absolute shortest path?
    #
    # Actually it's worse, because the distance metrix between two points is
    # the "as the crow flies" distance. Well actually its technically even worse, since
    # we don't take into account the curvature of the Earth. If you are doing routes
    # where that matters, more power to you, but this will be (more) inaccurate.
    # To solve some of these problems we could use the google maps distance matrix
    # api instead, which would be more realistic. However if we do this
    # naively we have to query n^2 number of pairs, where n is the number
    # of segments. Since the google maps distance matrix API only allows up
    # to 100 pairs each query, we would have to batch them. Moreover this
    # query is rather slow.
    #
    # For large number of segments we could do a heuristic where when finding the next
    # segment we only send the N closest segments per the straight line heuristic to
    # the distance matrix API.
    result = []
    origin = start_latlng
    remaining = set(range(0, len(segment_latlngs)))
    while (len(remaining) > 0):
        distances = []
        for i in range(0, len(segment_latlngs)):
            # Already visited this segment
            if i not in remaining: continue

            segment_latlng_start = segment_latlngs[i][0]

            # As the crow flies distance. If you are doing distances where the curvature of
            # the earth starts to matter, more power to you, but this won't work.
            distances = distances + (
              [(i,
                math.sqrt(pow(float(origin["lat"]) - float(segment_latlng_start["lat"]), 2) +
                          pow(float(origin["lng"]) - float(segment_latlng_start["lng"]), 2)))])

        # Sort by distance.
        distances.sort(key=(lambda a : a[1]))
        closest_index = distances[0][0]
        closest_next_segment = segment_latlngs[closest_index]

        # Take the closest as the next value, and its end point as the next start.
        result = result + [closest_next_segment]
        origin = closest_next_segment[len(closest_next_segment) - 1]
        remaining.remove(closest_index)
        indices.append(closest_index)

        if max_segments != -1 and len(segment_latlngs) - len(remaining) >= max_segments:
            break

    return result

def make_gpx(gmaps, start_latlng, segment_latlngs, output_file_name):
    latlngs = [start_latlng]
    for segment_latlng in segment_latlngs:
        # Go from previous point to start of segment
        latlngs = latlngs + get_directions(gmaps, latlngs[len(latlngs) -1], segment_latlng[0])

        # Go from start of segment to end
        latlngs =  latlngs + segment_latlng

    # Go from last segment back to first.
    latlngs = latlngs + get_directions(gmaps, latlngs[len(latlngs) -1], start_latlng)
    write_gpx(latlngs, output_file_name)

def main():
    parser = argparse.ArgumentParser(
        description="Determines a route from a selection of Strava segments"
    )

    parser.add_argument("--maps_api_key", type=str, required=True)
    parser.add_argument("--segments", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    parser.add_argument("--start_lat_lng", type=str, required=True)
    parser.add_argument("--strava_access_token", type=str, required=True)
    parser.add_argument("--max_segments", type=int, required=False, default=-1)

    args = parser.parse_args()
    segments = args.segments.split(',')
    (start_lat, start_lng) = args.start_lat_lng.split(',')
    start_latlng = start_latlng = {"lat": start_lat, "lng": start_lng}

    gmaps = googlemaps.Client(key=args.maps_api_key)

    indices = []
    segment_latlngs = [get_segment_latlngs(args.strava_access_token, s) for s in segments]
    segment_latlngs_ordered = get_segment_ordering(gmaps, start_latlng, segment_latlngs, args.max_segments, indices)

    make_gpx(gmaps, start_latlng, segment_latlngs_ordered, args.output_file)
    print([segments[i] for i in indices])

if __name__ == "__main__":
    main()
