# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import cint, cstr, nowdate

from erpnext.setup.doctype.item_group.item_group import get_item_for_list_in_html
from erpnext.e_commerce.shopping_cart.product_info import set_product_info_for_website

# For SEARCH -------
from redisearch import AutoCompleter, Client, Query
from erpnext.e_commerce.website_item_indexing import (
	WEBSITE_ITEM_INDEX, 
	WEBSITE_ITEM_NAME_AUTOCOMPLETE,
	WEBSITE_ITEM_CATEGORY_AUTOCOMPLETE,
	make_key
)
# -----------------

no_cache = 1


def get_context(context):
	context.show_search = True

@frappe.whitelist(allow_guest=True)
def get_product_list(search=None, start=0, limit=12):
	# limit = 12 because we show 12 items in the grid view

	# base query
	query = """select I.name, I.item_name, I.item_code, I.route, I.image, I.website_image, I.thumbnail, I.item_group,
			I.description, I.web_long_description as website_description, I.is_stock_item,
			case when (S.actual_qty - S.reserved_qty) > 0 then 1 else 0 end as in_stock, I.website_warehouse,
			I.has_batch_no
		from `tabItem` I
		left join tabBin S on I.item_code = S.item_code and I.website_warehouse = S.warehouse
		where (I.show_in_website = 1)
			and I.disabled = 0
			and (I.end_of_life is null or I.end_of_life='0000-00-00' or I.end_of_life > %(today)s)"""

	# search term condition
	if search:
		query += """ and (I.web_long_description like %(search)s
				or I.description like %(search)s
				or I.item_name like %(search)s
				or I.name like %(search)s)"""
		search = "%" + cstr(search) + "%"

	# order by
	query += """ order by I.weightage desc, in_stock desc, I.modified desc limit %s, %s""" % (cint(start), cint(limit))

	data = frappe.db.sql(query, {
		"search": search,
		"today": nowdate()
	}, as_dict=1)

	for item in data:
		set_product_info_for_website(item)

	return [get_item_for_list_in_html(r) for r in data]

@frappe.whitelist(allow_guest=True)
def search(query, limit=10, fuzzy_search=True):
	if not query:
		# TODO: return top searches
		return []

	red = frappe.cache()

	query = clean_up_query(query)

	ac = AutoCompleter(make_key(WEBSITE_ITEM_NAME_AUTOCOMPLETE), conn=red)
	client = Client(make_key(WEBSITE_ITEM_INDEX), conn=red)
	suggestions = ac.get_suggestions(
		query, 
		num=limit, 
		fuzzy= fuzzy_search and len(query) > 4 # Fuzzy on length < 3 can be real slow
	)

	# Build a query
	query_string = query

	for s in suggestions:
		query_string += f"|('{clean_up_query(s.string)}')"

	q = Query(query_string)

	print(f"Executing query: {q.query_string()}")

	results = client.search(q)
	results = list(map(convert_to_dict, results.docs))

	# FOR DEBUGGING
	print("SEARCH RESULTS ------------------\n ", results)

	return results

def clean_up_query(query):
	return ''.join(c for c in query if c.isalnum() or c.isspace())

def convert_to_dict(redis_search_doc):
	return redis_search_doc.__dict__

@frappe.whitelist(allow_guest=True)
def get_category_suggestions(query):
	if not query:
		# TODO: return top searches
		return []

	ac = AutoCompleter(make_key(WEBSITE_ITEM_CATEGORY_AUTOCOMPLETE), conn=frappe.cache())
	suggestions = ac.get_suggestions(query, num=10)

	return [s.string for s in suggestions]