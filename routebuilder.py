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
import heldkarp

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

def get_segment_information(strava_access_token, segment_id):
  filename = "segment_information/{}.json".format(segment_id)
  if not path.exists(filename):
      segmentdownloader.download_segment_latlngs(strava_access_token, segment_id)

  with open(filename, "r") as file:
    segment_json = json.loads(file.read())
    segment_polyline = segment_json["map"]["polyline"]
    segment_length = segment_json["distance"]
    segment_latlngs = googlemaps.convert.decode_polyline(segment_polyline)
    return {"length": segment_length, "latlngs" : segment_latlngs}

def get_directions(gmaps, start_latlng, end_latlng):
    directions_result = gmaps.directions(start_latlng, end_latlng, mode="bicycling")
    polyline = directions_result[0]["overview_polyline"]["points"]
    return googlemaps.convert.decode_polyline(polyline)

def get_segment_ordering_heldkarp(gmaps, start_latlng, segment_information, indices):
    # 2N segments. Need to include from start of a segment to end of a segment, but
    # there is only one path there.
    start_and_segment_information = [{'length': 1, 'latlngs': [start_latlng, start_latlng]}] + segment_information
    number_of_points = 1 + len(segment_information)
    distances = [[0] * number_of_points for i in range(number_of_points)]
    segment_distances = []
    for i in range(len(start_and_segment_information)):
        origin_latlngs = start_and_segment_information[i]["latlngs"]

        # Start at the end
        origin = origin_latlngs[len(origin_latlngs) - 1]

        # Compute distance of end of this segment to start of all the other ones.
        destination_segment_information = start_and_segment_information[:i] + start_and_segment_information[i+1:]
        destinations = [x["latlngs"][0] for x in destination_segment_information]
        matrix = gmaps.distance_matrix([origin], destinations, mode="bicycling", units="metric")
        distance_destinations = matrix["rows"][0]['elements']

        for j in range(len(start_and_segment_information)):
            if i == j: continue
            elif j > i: destination_index = j-1
            else: destination_index = j

            # Go from end to start of next value.
            distance_destination = distance_destinations[destination_index]["distance"]["value"]
            distances[i][j] = distance_destination + start_and_segment_information[j]["length"]

    print("Completed constructing distance matrix")
    path = heldkarp.held_karp(distances)
    result = []
    for i in path:
        if i == 0: continue
        else:
            indices.append(i-1)
            result.append(segment_information[i-1]["latlngs"])
    return result

def get_segment_ordering_greedy(gmaps, start_latlng, segment_latlngs, max_segments, indices):
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

        # Get the actual distances for the then closest.
        top_ten_destinations = [segment_latlngs[i][0] for (i, _) in distances[:10]]
        matrix = gmaps.distance_matrix([origin], top_ten_destinations, mode="bicycling")
        distance_destinations = matrix["rows"][0]['elements']
        indices_sorted = sorted(range(len(distance_destinations)),
                                 key=lambda k: distance_destinations[k]["distance"]["value"])

        closest_index = distances[indices_sorted[0]][0]
        closest_next_segment = segment_latlngs[closest_index]

        # Take the closest as the next value, and its end point as the next start.
        result = result + [closest_next_segment]
        origin = closest_next_segment[len(closest_next_segment) - 1]
        remaining.remove(closest_index)
        indices.append(closest_index)

        if max_segments != -1 and len(segment_latlngs) - len(remaining) >= max_segments:
            break

    return result

def make_gpx(gmaps, start_latlng, next_latlng, segment_latlngs, output_file_name):
    latlngs = [start_latlng]
    if (next_latlng is not None):
        latlngs = latlngs + get_directions(gmaps, start_latlng, next_latlng)
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
    parser.add_argument("--next_point", type=str, required=False, default=None)
    parser.add_argument("--heldkarp", type=bool, required=False, default=False)

    args = parser.parse_args()
    segments = args.segments.split(',')
    (start_lat, start_lng) = args.start_lat_lng.split(',')
    start_latlng = start_latlng = {"lat": start_lat, "lng": start_lng}

    if args.next_point is not None:
        (next_lat, next_lng) = args.next_point.split(',')
        next_latlng = {"lat": next_lat, "lng": next_lng}
    else: next_latlng = None

    gmaps = googlemaps.Client(key=args.maps_api_key)

    indices = []
    segment_information = [get_segment_information(args.strava_access_token, s) for s in segments]

    # This is sadly so slow as to never really be useful :(
    if not args.heldkarp:
        segment_latlngs_ordered = get_segment_ordering_greedy(
            gmaps, next_latlng if next_latlng is not None else start_latlng,
            [x["latlngs"] for x in segment_information], args.max_segments, indices)
    else:
        segment_latlngs_ordered = get_segment_ordering_heldkarp(
            gmaps, next_latlng if next_latlng is not None else start_latlng, segment_information, indices)

    make_gpx(gmaps, start_latlng, next_latlng, segment_latlngs_ordered, args.output_file)
    print([segments[i] for i in indices])

if __name__ == "__main__":
    main()
