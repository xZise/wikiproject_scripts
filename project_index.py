# -*- coding: utf-8 -*-
"""
Project Index -- prepares an index of WikiProjects and their in-scope pages for use by scripts
Copyright (C) 2015 James Hare
Licensed under MIT License: http://mitlicense.org
"""

import pymysql
import re


class WikiProjectTools:
    def metaquery(self, connection, sqlquery, values):
        """Carries out MySQL queries"""
        cur = connection.cursor()
        cur.execute(sqlquery, values)
        data = []
        for row in cur:
            data.append(row)
        return data

    def wikiquery(self, sqlquery, values):
        """Constructs a MySQL query to the Tool Labs database replica."""
        conn = pymysql.connect(host='enwiki.labsdb', port=3306, db='enwiki_p', read_default_file='~/.my.cnf', charset='utf8')
        data = self.metaquery(conn, sqlquery, values)
        return data

    def indexquery(self, sqlquery, values):
        """Constructs a MySQL query to the WPX database."""
        conn = pymysql.connect(host='tools-db', port=3306, db='s52475__wpx', read_default_file='~/.my.cnf', charset='utf8')
        data = self.metaquery(conn, sqlquery, values)
        conn.commit()
        return data

    def masterlist(self):
        """
        Prepares the master list of WikiProject quality assessment categories.
        Returns a dictionary of lists, with the key being the page_title of the WikiProject (or task force)
        and the value being a list of categories.
        """

        query = self.wikiquery('select page_title from page where page_namespace = 14 and (page_title like "%-Class_%_articles" or page_title like "Unassessed_%_articles" or page_title like "WikiProject_%_articles") and page_title not like "%-importance_%" and page_title not like "Wikipedia_%" and page_title not like "Template-%" and page_title not like "Redirect-%" and page_title not like "Project-%" and page_title not like "Portal-%" and page_title not like "File-%" and page_title not like "FM-%" and page_title not like "Category-%" and page_title not like "Cat-%" and page_title not like "Book-%" and page_title not like "NA-%" and page_title not like "%_Operation_Majestic_Titan_%" and page_title not like "%_Version_%" and page_title not like "All_Wikipedia_%" and page_title not like "%_Wikipedia-Books_%" and page_title not like "Assessed-%" and page_title not like "%-Priority_%" and page_title not like "Unassessed_field_%" and page_title not like "Unassessed_importance_%" and page_title not like "Unassessed-Class_articles" and page_title not like "%_Article_quality_research_articles" and page_title not like "WikiProject_lists_of_encyclopedic_articles";', None)
        categories = []
        for row in query:
            categories.append(row[0].decode('utf-8'))

        # Record in a dictionary of lists? wikiprojects = {'Military history': ['Category:A', 'Category:B']}
        buckets = {}

        for category in categories:
            projectname = category
            projectname = projectname.replace('WikiProject_', '') # Some categories include "WikiProject" in the category name.
            projectname = projectname.replace('-related', '') # e.g. "Museum-related" -> "Museum"
            projectname = projectname.replace('_quality', '') # e.g. "Unassessed_quality" -> "Unassessed"
            projectname = projectname.replace('_subproject_selected_articles', '')
            projectname = projectname.replace('_automatically_assessed', '')
            projectname = re.sub(r'_task_?forces?(_by)?', '', projectname)
            projectname = re.sub(r'_work_?group', '', projectname)
            projectname = re.sub(r'_articles$', '', projectname)
            projectname = re.sub(r'_newsletter$', '', projectname)
            projectname = re.sub(r'^((.*)-Class|Unassessed)_', '', projectname)
            projectname = projectname[0].upper() + projectname[1:] # Capitalize the first letter
            try:
                buckets[projectname].append(category)
            except KeyError:
                buckets[projectname] = []
                buckets[projectname].append(category)

        # For each key in buckets, try to match it to a real WikiProject or task force name
        # Checks against the redirect table so that it can follow redirects

        pagetitles = {}
        namespaces = {2: 'User:', 3: 'User_talk:', 4: 'Wikipedia:', 5: 'Wikipedia_talk:', 100: 'Portal:', 101: 'Portal_talk:'}
        # Heavens help me if WikiProjects end up in namespaces other than those.

        for key in buckets.keys():
            project_area = key
            query = self.wikiquery('select page.page_title,redirect.rd_namespace,redirect.rd_title from page left join redirect on redirect.rd_from = page.page_id where page_title = %s and page_namespace = 4;', ('WikiProject_'+key,))
            if len(query) == 0:
                query = self.wikiquery('select page.page_title,redirect.rd_namespace,redirect.rd_title from page left join redirect on redirect.rd_from = page.page_id where page_title = %s and page_namespace = 4;', ('WikiProject_'+key+'s',)) # Checks for plural
                if len(query) == 0:
                    print('Warning: No project page found for key: ' + key)
                    continue

            page_title = query[0][0]
            rd_namespace = query[0][1]
            rd_title = query[0][2]

            if rd_title is not None:
                pagetitles[key] = namespaces[rd_namespace] + rd_title.decode('utf-8')
            elif rd_title is None and page_title is not None:
                pagetitles[key] = namespaces[4] + page_title.decode('utf-8')

        # At this point, each key of buckets should be tied to an actual page name
        output = {}

        for key in buckets.keys():
            for category in buckets[key]:
                # TODO: Use a collections.defaultdict here
                try:
                    output[pagetitles[key]].append(category)
                except KeyError:
                    output[pagetitles[key]] = []
                    output[pagetitles[key]].append(category)

        return output

    def projectscope(self, project,categories):
        """
        Returns a list of articles in the scope of a WikiProject
        Requires the string 'project' and the list 'categories'
        """

        query_builder = 'select distinct page.page_title,page.page_namespace from categorylinks join page on categorylinks.cl_from=page.page_id where page_namespace in (1, 119) and cl_to in ('
        mastertuple = ()
        for category in categories:
            query_builder += '%s, '
            mastertuple += (category,)
        query_builder = query_builder[:-2] # Truncate extraneous "or"
        query_builder += ');' # Wrap up query

        query = self.wikiquery(query_builder, mastertuple)
        namespaces = {1: "Talk:", 119: "Draft_talk:"}
        output = []

        for row in query:
            page_title = row[0].decode('utf-8')
            page_namespace = namespaces[row[1]]
            output.append(page_namespace + page_title)

        return output

    def main(self):
        # Prepare list of WikiProjects and their categories
        print('Preparing master list of WikiProjects...')
        wikiprojects = self.masterlist()

        # Get list of pages for each WikiProject
        print('Getting list of pages for each WikiProject...')
        pages = {}
        for wikiproject in wikiprojects.keys():
            pages[wikiproject] = self.projectscope(wikiproject, wikiprojects[wikiproject])

        dbinput = []
        for wikiproject in pages.keys():
            for page in pages[wikiproject]:
                dbinput.append((page, wikiproject))

        # Saves it to the database
        print('Saving to the database...')
        self.indexquery('create table projectindex_draft (pi_id int(11) NOT NULL auto_increment, pi_page VARCHAR(255) character set utf8 collate utf8_unicode_ci, pi_project VARCHAR(255) character set utf8 collate utf8_unicode_ci, primary key (pi_id)) engine=innodb character set=utf8;', None)

        packages = []
        for i in range(0, len(dbinput), 10000):
            packages.append(dbinput[i:i+10000])

        counter = 0
        for package in packages:
            query_builder = 'insert into projectindex_draft (pi_page, pi_project) values ' # seeding really long query
            mastertuple = ()
            for item in package:
                query_builder += '(%s, %s), '
                mastertuple += item
            query_builder = query_builder[:-2] # truncating the terminal comma and space
            query_builder += ';'
            counter += 1
            print('Executing batch query no. ' + str(counter))
            self.indexquery(query_builder, mastertuple)

        self.indexquery('drop table if exists projectindex', None)
        self.indexquery('rename table projectindex_draft to projectindex', None) # Moving draft table over to live table

if __name__ == "__main__":
    wptools = WikiProjectTools()
    wptools.main()
