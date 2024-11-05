# A quick python script to extract your energy expenditure from a GPX file.
It will spit out estimated calories used, and optionally a graph with altitude and power used at any point of your walk.

It uses the gpxz API to get more accurate terrain data if your altitude isn't accurate, you can get a free API key here:
https://www.gpxz.io/

It is heavily inspired by this article, I put together the code and added some cool stuff to it :D
https://www.gpxz.io/blog/hiking-energy-expenditure

Take a look at the settings first! you can set your weight, and a few other things.
Usage: python g2e.py filename.gpx
