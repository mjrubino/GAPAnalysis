def ProcessRichness(spp, groupName, outLoc, modelDir, season, interval_size, CONUS_extent, 
                    snap_raster, expand=False):    
    '''
    (list, str, str, str, str, int, str) -> str, str

    Creates a species richness raster for the passed species. Also includes a
      table listing all the included species. Intermediate richness rasters are
      retained. That is, the code processes the rasters in groups of the given interval
      size, to keep from overloading ArcPy's cell statistics function; the intermediate
      richness rasters are retained for spot-checking and for potential re-running of 
      species subsets. Refer to the output log file for a list of species included in 
      each intermediate raster as well as the code that was run for the process.

    Returns the path to the output richness raster and the path to the species
      table.

    Arguments:
    spp -- A list of GAP species codes to include in the calculation
    groupName -- The name you wish to use to identify the output directories
        and files (e.g., 'raptors')
    outLoc -- The directory in which you wish to place output and intermediate files.
    modelDir -- The directory that holds all of the GAP habitat map .tifs needed for the 
        analysis.
    season -- Seasonal criteris for reclassifying the output.  Choose "Summer", "Winter", 
        or "Any". "Any" will reclassify output so that any value > 0 gets reclassed to "1" and
        is the default. 
    interval_size -- How many rasters to include in an intermediate batch.  20 is a good number.
    expand -- Default to False.  If you set to true, then each reclassed raster will be added to
        a raster of CONUS extent with the top, left 9 pixels having a value of 1, and all others 
        with a value of zero.  Doing this provides a check that each model was added during the 
        processing, but it slows things down A LOT.  The CONUS extent grid lives in the GAPage
        data directory.
    CONUS_extent -- A raster with a national/CONUS extent, and all cells have value of 0 except 
        for a 3x3 cell square in the top left corner that has values of 1.  The spatial reference
        should be NAD_1983_Albers and cell size 30x30 m.
    snap_raster -- A 30x30m cell raster to use as a snap grid during processing.

    Example:
    >>> ProcessRichness(['aagtox', 'bbaeax', 'mnarox'], 'MyRandomSpecies', 
                        outLoc='C:/GIS_Data/Richness', modelDir='C:/Data/Model/Output',
                        season="Summer", interval_size=20, 
                        log='C:/GIS_DATA/Richness/log_MyRandomSpecies.txt')
    C:\GIS_Data\Richness\MyRandomSpecies_04_Richness\MyRandomSpecies.tif, C:\GIS_Data\Richness\MyRandomSpecies.csv
    '''    
    
    import os, datetime, arcpy, shutil 
    arcpy.CheckOutExtension('SPATIAL')
    arcpy.env.overwriteOutput=True
    arcpy.env.extent = "MAXOF" 
    arcpy.env.pyramid = 'NONE'
    arcpy.env.snapRaster = CONUS_extent
    arcpy.env.rasterStatistics = "STATISTICS"
    arcpy.env.cellSize = 30
    starttime = datetime.datetime.now()      
    
    # Maximum number of species to process at once
    interval = interval_size
    # Initialize an empty list to store the intermediate richness rasters
    richInts = []
    # Count the number of species in the species list
    sppLength = len(spp)
    
    ############################################# create directories for the output
    ###############################################################################
    outDir = os.path.join(outLoc, groupName)    
    scratch = os.path.join(outDir,'_scratch')
    reclassDir = os.path.join(outDir, '_reclassed')
    intDir = os.path.join(outDir, 'Richness_intermediates')
    for x in [scratch, reclassDir, intDir, outDir]:
        if not os.path.exists(x):
            os.makedirs(x)
    log = outDir+"/Log{0}.txt".format(groupName)
    if not os.path.exists(log):
        logObj = open(log, "wb")
        logObj.close()
    
    ######################################## Function to write data to the log file
    ###############################################################################
    def __Log(content):
        print content
        with open(log, 'a') as logDoc:
            logDoc.write(content + '\n')
    
    ############################### Write a table with species included in a column
    ###############################################################################
    outTable = os.path.join(outDir, groupName + '.csv')
    spTable = open(outTable, "a")
    for s in spp:
        spTable.write(str(s) + ",\n")
    spTable.close()
    
    ###################################################### Write header to log file
    ###############################################################################
    __Log("WARNING!!!  This module uses the arcpy Cell Statistics tool, which is known \
            to provide slightly inconsistent and incorrect answers.")    
    __Log("\n" + ("#"*67))
    __Log("The results from richness processing")
    __Log("#"*67)    
    __Log(starttime.strftime("%c"))
    __Log('\nProcessing {0} species as "{1}".\n'.format(sppLength, groupName).upper())
    __Log('Season of this calculation: ' + season)
    __Log('Table written to {0}'.format(outTable))
    __Log('\nThe species that will be used for analysis:')
    __Log(str(spp) + '\n')
    
    ####### Create dictionary to collect raster tables for use in checking the count 
    ################################# of cells in the original vs. reclassed rasters
    startTifTables = {}
    
    ############  Process the batches of species to make intermediate richness maps
    ###############################################################################
    # Iterate through the list interval # at a time
    for x in range(0, sppLength, interval):
        # Grab a subset of species
        sppSubset = spp[x:x+interval]
        # Get the length of the subset for use in error checking later
        groupLength = len(sppSubset)
        # Assigned the species subset a name
        gn = '{0}_{1}'.format(groupName, x)
        # Process the richness for the subset of species
        __Log('\nProcessing {0}: {1}'.format(gn, sppSubset))  
              
        #########################################  Copy models to scratch directory
        ###########################################################################
        __Log('\tCopying models to scratch directory')
        # Initialize an empty list to store paths to the local models
        sppLocal = list()
        # For each species
        for sp in sppSubset:
            arcpy.env.extent = "MAXOF"
            # Get the path to the species' raster
            sp = sp.lower()
            startTif = modelDir + "/" + sp
            # Set the path to the local raster
            spPath = os.path.join(scratch, sp)
            # If the species does not have a raster, print a
            # warning and skip to the next species
            if not arcpy.Exists(startTif):
                __Log('\tWARNING! The species\' raster could not be found -- {0}'.format(sp))
                raw_input("Fix, then press enter to resume")
            spObj = arcpy.Raster(startTif)
            
            # Build a dictionary to store RAT of initial map for error checking later
            startTifTable = {}
            startTifCursor = arcpy.SearchCursor(spObj)
            for row in startTifCursor:
                startTifTable[row.getValue("VALUE")] = row.getValue("COUNT")
            anyCount = sum(startTifTable.values())
            if 2 in startTifTable and 3 in startTifTable:
                winterCount = startTifTable[2] + startTifTable[3]
                summerCount = startTifTable[3] + (anyCount - winterCount)
            if 2 in startTifTable and 3 not in startTifTable:
                winterCount = startTifTable[2]
                summerCount = anyCount - winterCount
            if 2 not in startTifTable and 3 in startTifTable:
                winterCount = startTifTable[3]
                summerCount = startTifTable[3]
            if 1 in startTifTable and 3 in startTifTable:
                summerCount = startTifTable[1] + startTifTable[3]
                winterCount = startTifTable[3] + (anyCount - summerCount)
            if 1 in startTifTable and 3 not in startTifTable:
                summerCount = startTifTable[1]
                winterCount = anyCount - summerCount
            if 1 not in startTifTable and 3 in startTifTable:
                summerCount = startTifTable[3]
                winterCount = startTifTable[3]
            startTifTables[sp] = {}
            startTifTables[sp]["anyCount"] = anyCount
            startTifTables[sp]["summerCount"] = summerCount
            startTifTables[sp]["winterCount"] = winterCount
            
            # Check that the species has cells with the desired seasonal value, if
            # so, copy to scratch directory.
            if season == "Winter" and spObj.maximum == 1 and spObj.minimum == 1:
                __Log("\t\t\t{0} doesn't have any winter habitat, skipping...".format(sp))
                # Deduct this model from count of the subset
                groupLength = groupLength - 1
                sppLength = sppLength - 1  
            elif season == "Summer" and spObj.maximum == 2 and spObj.minimum == 2:
                __Log("\t\t\t{0} doesn't have any summer habitat, skipping...".format(sp))
                # Deduct this model from count of the subset
                groupLength = groupLength - 1
                sppLength = sppLength - 1
            else:            
                try:
                    # Copy the species' raster from the  species model output directory to 
                    # the local drive
                    arcpy.management.CopyRaster(startTif, spPath, nodata_value=0, 
                                                pixel_type="2_BIT")
                    __Log('\t\t{0}'.format(sp))
                    # Add the path to the local raster to the list of species rasters
                    sppLocal.append(spPath)    
                except Exception as e:
                    __Log('ERROR in copying a model - {0}'.format(e))
        __Log('\tAll models copied to {0}'.format(scratch))
      
       ############################################  Reclassify the batch of models
       ############################################################################
       # Get a list of models to reclassify
        arcpy.env.workspace = reclassDir
        __Log('\tReclassifying')
        # Initialize an empty list to store the paths to the reclassed rasters
        sppReclassed = list()
        # Assign SQL statements for reclass condition
        if season == "Summer":
            wc = "VALUE = 1 OR VALUE = 3"
        elif season == "Winter":
            wc = "VALUE = 2 OR VALUE = 3"
        elif season == "Any":
            wc = "VALUE > 0"
        # For each of the local species rasters....
        for sp in sppLocal:
            ################################################################ Reclassify 
            ###########################################################################             
            try:
                __Log('\t\t{0}'.format(os.path.basename(sp)))
                # Set a path to the output reclassified raster
                reclassed = os.path.join(reclassDir, os.path.basename(sp))
                # Make sure that the copied model exists, pause if not.
                if not arcpy.Exists(sp):
                    __Log('\tWARNING! The species\' raster could not be found -- {0}'.format(sp))
                    raw_input("Fix, then press enter to resume")
                # Create a temporary raster from the species' raster, setting all
                # values meeting the condition to 1
                tempRast = arcpy.sa.Con(sp, 1, where_clause = wc)
                # Check that the reclassed raster has valid values (should be 1's and nodatas),
                # first build statistics
                arcpy.management.CalculateStatistics(in_raster_dataset=tempRast, skip_existing=True)
            except Exception as e:
                __Log('ERROR in reclassifying a model - {0}'.format(e))
            
            ########################################## Optional: expand to CONUS extent
            ###########################################################################
            try:
                if expand == True:
                    tempRast = arcpy.sa.CellStatistics([tempRast, CONUS_extent], 
                                                        "SUM", "DATA")
            except Exception as e:
                __Log('ERROR expanding reclassed raster - {0}'.format(e))
            
            ############################################## Save the reclassified raster
            ###########################################################################
            tempRast.save(reclassed)
            # Add the reclassed raster's path to the list
            sppReclassed.append(reclassed)
            # Make sure that the reclassified model exists.
            if not arcpy.Exists(reclassed):
                __Log('\tWARNING! This reclassed raster could not be found -- {0}'.format(sp))   
           
            ############################################## Check the values of tempRast
            ###########################################################################
            # Check min, max, and mean values                
            if tempRast.minimum != 1:
                __Log('\t\t\tWARNING! Invalid minimum cell value -- {0}'.format(sp))
            elif tempRast.minimum == 1:
                __Log('\t\t\tValid minimum cell value')
            if tempRast.maximum != 1:
                __Log('\t\t\tWARNING! Invalid maximum cell value -- {0}'.format(sp))
            elif tempRast.maximum == 1:
                __Log('\t\t\tValid maximum cell value')
            if tempRast.mean != 1:
                __Log('\t\t\tWARNING! Invalid mean cell value -- {0}'.format(sp))
            elif tempRast.mean == 1:
                __Log('\t\t\tValid mean cell value')
            # Check the count of the reclassed raster against the original, expect errors
            # if grid has over 2 billion cells bcs. VAT can't be built
            try:
                tempRastTable = {}
                tempRastCursor = arcpy.SearchCursor(tempRast)
                for row in tempRastCursor:
                    tempRastTable[row.getValue("VALUE")] = row.getValue("COUNT")
                    # Delete the row and cursor to avoid a lingering .lock file
                    del row
                del tempRastCursor
                tempRast = None
                if season == "Any" and tempRastTable[1] != startTifTables[sp[-10:]]["anyCount"]:
                    __Log("\t\t\tWARNING! incorrect total cell count in reclass of {0}".format(sp[-10:]))
                    __Log("\t\tReclassed count = {0}, initial geotiff count = {1}".format(tempRastTable[1], startTifTables[sp[-10:]]["anyCount"]))
                elif season == "Summer" and tempRastTable[1] != startTifTables[sp[-10:]]["summerCount"]:
                    __Log("\t\t\tWARNING! incorrect total cell count in reclass of {0}".format(sp[-10:]))
                    __Log("\t\tReclassed count = {0}, initial geotiff count = {1}".format(tempRastTable[1], startTifTables[sp[-10:]]["summerCount"]))
                elif season == "Winter" and tempRastTable[1] != startTifTables[sp[-10:]]["winterCount"]:
                    __Log("\t\t\tWARNING! incorrect total cell count in reclass of {0}".format(sp[-10:]))
                    __Log("\t\tReclassed count = {0}, initial geotiff count = {1}".format(tempRastTable[1], startTifTables[sp[-10:]]["winterCount"]))
                else:
                    __Log("\t\t\tValid cell count")
            except Exception as e:
                __Log("Couldn't check the total cell count of {0}".format(e))  
        __Log('\tAll models reclassified')
    
        ########################################  Calculate richness for the subset
        ###########################################################################
        try:
            arcpy.env.extent = arcpy.Extent(-2361141.227, 262172.07799999975, 2262968.773,
                                            3177272.0779999997)  
            richness = arcpy.sa.CellStatistics(sppReclassed, 'SUM', 'DATA')
            __Log('\tRichness processed')
            outRast = os.path.join(intDir, gn + '.tif')
            richness.save(outRast)
            arcpy.management.BuildRasterAttributeTable(in_raster=outRast, overwrite=True)
            __Log('\tSaved to {0}'.format(outRast))
            # Check the max value.  It shouldn't be > the group length.
            if richness.maximum > groupLength:
                __Log('\tWARNING! Invalid maximum cell value in {0}'.format(gn))
            # Add the subset's richness raster to the list of intermediate rasters
            richInts.append(outRast)
        except Exception as e:
            __Log('ERROR in making intermediate richness - {0}'.format(e))
        
        ########### If the expand option used, check max count to see if it's right
        ###########################################################################
        if expand == True:
            try:
                __Log('Checking intermediate raster count')        
                if richness.maximum != groupLength:
                    __Log('A raster was skipped in intermediate richness calculation...quiting')
                    quit
                elif richness.maximum == groupLength:
                    __Log('Intermediate richness used the right number of rasters')
            except Exception as e:
                __Log('ERROR in checking intermediate richness raster count - {0}'.format(e))
        
        ################  Delete each of the copied and reclassified species models
        ###########################################################################
        try:
            for rast in sppReclassed:
                arcpy.Delete_management(rast)
            for sp in sppSubset:
                arcpy.Delete_management(os.path.join(scratch, sp))
        except Exception as e:
            __Log('ERROR in deleting intermediate models - {0}'.format(e))
         
    #################  Sum the intermediate rasters to calculate the final richness
    ###############################################################################
    try:
        arcpy.env.extent = arcpy.Extent(-2361141.227, 262172.07799999975, 2262968.773, 
                            3177272.0779999997)  
        __Log('Calculating final richness')
        richness = arcpy.sa.CellStatistics(richInts, 'SUM', 'DATA')
        __Log('Richness calculated')
        outRast = os.path.join(outDir, groupName + '.tif')
        __Log('Saving richness raster to {0}'.format(outRast))
        richness.save(outRast)
        __Log('Richness raster saved.')    
    except Exception as e:
        __Log('ERROR in final richness calculation - {0}'.format(e))
    
    ############# If the expand option used, check max count to see if it right
    ###########################################################################
    if expand == True:
        try:
            __Log('Checking final richness raster count')        
            if richness.maximum != sppLength:
                __Log('A raster(s) was skipped somewhere...quiting')
                quit
            elif richness.maximum == sppLength:
                __Log('Final richness has the right number of rasters')
        except Exception as e:
            __Log('ERROR in checking intermediate richness raster count - {0}'.format(e))
    
    shutil.rmtree(scratch)
    shutil.rmtree(reclassDir)
    endtime = datetime.datetime.now()
    runtime = endtime - starttime
    __Log("Total runtime was: " + str(runtime))

    return outRast, outTable