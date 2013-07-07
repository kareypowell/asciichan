import os
import re
import sys
import logging
from urllib2 import Request, urlopen, URLError
from xml.dom import minidom

import webapp2
import jinja2

from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.api import urlfetch

DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Development')

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

art_key = db.Key.from_path('ASCIIChan', 'arts')

def console(s):
	sys.stderr.write('%s\n' % s)

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

class BaseHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **kw):
    	t = jinja_env.get_template(template)
    	return t.render(params)

    def render(self, template, **kw):
        self.response.out.write(render_str(template, **kw))

GMAPS_URL = "http://maps.googleapis.com/maps/api/staticmap?size=380x263&sensor=false&"
def gmaps_img(points):
    markers = '&'.join('markers=%s,%s' % (p.lat, p.lon) for p in points)
    return GMAPS_URL + markers

IP_URL = "http://api.hostip.info/?ip="
def get_coordinates(ip):
	# check if we are in the development env, if so, then use default Ip
	if DEBUG:
		# ip = "4.2.2.2"
		ip = "23.24.209.141"
		# ip = "216.10.223.172"
	
	url = Request(IP_URL + ip)
	content = None
	try:
		content = urlopen(url).read()
	except URLError:
		return

	if content:
		d = minidom.parseString(content)
		coords = d.getElementsByTagName("gml:coordinates")
		if coords and coords[0].childNodes[0].nodeValue:
			lon, lat = coords[0].childNodes[0].nodeValue.split(",")
			return db.GeoPt(lat, lon)

class Art(db.Model):
	title = db.StringProperty(required = True)
	art = db.TextProperty(required = True)
	coords = db.GeoPtProperty()
	created = db.DateTimeProperty(auto_now_add = True)

def top_arts(update = False):
	key = "top"
	arts = memcache.get(key)
	if arts is None or update:
		logging.error("DB QUERY")
		arts = db.GqlQuery("SELECT * "
						   "FROM Art "
						   "WHERE ANCESTOR IS :1 "
						   "ORDER BY created DESC "
						   "LIMIT 10",
						   art_key)
		# prevent the running of multiple queries
		arts = list(arts)
		memcache.set(key, arts)
	return arts 

class MainPage(BaseHandler):

	def render_front(self, title = "", art = "", error = ""):
		arts = top_arts()

		# find which arts have coordinates
		points = filter(None, (a.coords for a in arts))

		# if we have any arts coords, make an image url
		img_url = None
		if points:
			img_url = gmaps_img(points)

		self.render("front.html", title = title, art = art, error = error, 
								arts = arts, img_url = img_url)

	def get(self):
		# self.write(repr(get_coordinates(self.request.remote_addr)))
		self.render_front()

	def post(self):
		title = self.request.get("title")
		art = self.request.get("art")

		if title and art:
			art = Art(parent = art_key, title = title, art = art)
			coords = get_coordinates(self.request.remote_addr)

			if coords:
				art.coords = coords

			art.put()
			top_arts(True)

			self.redirect("/")
		else:
			error = "we need both a title and some artwork!"
			self.render_front(title, art, error)


app = webapp2.WSGIApplication([('/', MainPage)], debug=True)