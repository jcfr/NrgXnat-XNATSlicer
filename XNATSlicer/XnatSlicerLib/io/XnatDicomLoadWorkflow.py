import imp, os, inspect, sys, slicer

from XnatLoadWorkflow import *
import DICOMScalarVolumePlugin 




comment = """
XnatDicomLoadWorkflow is the loader class for all DICOM input received
from XNAT.  The high-level workflow of the download is as follows:

1) Download a zip file of one scan or multiple scans in DICOM format.
2) Unpack the zip file and cache accordingly.
3) Apply these files to the slicer DICOM database.
4) Leverage the slicer 'DICOMWidget' to parse and and load the images.

NOTE: DICOMLoader makes use of Slicer's DICOM database and 
Steve Pieper's DICOMPlugin for parsing.

TODO:
"""




class XnatDicomLoadWorkflow(XnatLoadWorkflow):
    """ XnatDicomLoadWorkflow conducts the necessary steps
        to load DICOM files into Slicer.
    """
    
    def initLoad(self, args):
        """ Starter function for loading DICOMs into Slicer from
            XNAT.  The function 'load' is its successor.  This function
            determines if the user is downloading a single folder or multiple dicom
            folders.
        """

        self.processingDicomsMessageBox = qt.QMessageBox(1, "Processing data", "Processing.  Data will load automatically.")
        self.processingDicomsMessageBox.setWindowModality(1)
        self.processingDicomsMessageBox.setStandardButtons(0)


                
        #--------------------
        # Make sure Slicer's DICOMdatabase is set up.
        # Show a popup informing the user if it's not.
        # The user has to restart the process if it's not.
        #--------------------
        m = slicer.util.mainWindow()
        if not slicer.dicomDatabase:
            msg =  """It doesn\'t look like your DICOM database directory is setup. Please set it up in the DICOM module and try your download again."""
            self.terminateLoad(['DICOM load', msg ])
            m.moduleSelector().selectModule('DICOM')    




        #--------------------
        # Call parent class -- sets relevant public
        # variables.
        #--------------------
        super(XnatDicomLoadWorkflow, self).load(args)


        
        #--------------------
        # Define public vars. for XnatDicomLoadWorkflow.
        #--------------------
        self.XnatLevel = ''
        if '/scans/' in self.xnatSrc:
            self.XnatLevel = 'scans'
        elif '/experiments/' in self.xnatSrc:
            self.XnatLevel = 'experiments'
        elif '/subjects/' in self.xnatSrc:
            self.XnatLevel = 'subjects'
        self.folderName = os.path.basename(os.path.dirname(self.xnatSrc))
        self.downloadables = []
        self.DICOMWidget = None



        #---------------------
        # Is the user downloading multiple folders?
        #---------------------
        if self.xnatSrc.endswith("files"):
            
            #
            # If not, proceed with load at the current URI 
            # (contianed in 'args' argument)
            #
            self.load()
        else:
            
            #
            # If so, then setup+show dialog asking user if they
            # want to proceed.
            #
            self.areYouSureDialog = qt.QMessageBox()
            self.areYouSureDialog.setIcon(4)

            self.areYouSureDialog.setText("You are about to load all of " +   
                                          self.folderName + "'s "+  
                                          "DICOMs.\n" + 
                                          "This may take several minutes.\n" +
                                          "Are you sure you want to continue?")
            self.areYouSureDialog.addButton(qt.QMessageBox.Yes)
            self.areYouSureDialog.addButton(qt.QMessageBox.No)
            self.areYouSureDialog.connect('buttonClicked(QAbstractButton*)', self.load)
            self.areYouSureDialog.show()


            
            
    def getDownloadables(self, parentXnatUri):
        """ Called within the 'load' function. Checks if DICOM 
            files exist at the 'resources' level of a given XNAT path.
        """

        #---------------------
        # Get the resources of the Xnat URI provided in the argument.
        #---------------------

        contents = self.MODULE.XnatIo.getFolderContents(parentXnatUri + '/files', metadataTags = ['URI'])
        

        try:
            contents['URI']
        except Exception, e:
            print "Skipping '%s' (Error: %s)"%(fileFolderUri, str(e))
            #return

            
        #
        # Check to see if the file extensions (contents) are valid.
        #
        for filename in contents['URI']:
                
            #
            # If valid, add to "downloadables" if DICOM
            #
            print "Seeing if DICOM", filename
            if self.MODULE.utils.isDICOM(filename):
                self.downloadables.append(filename)                
            else:
                print  "%s Not a usable file: '%s' "%(self.MODULE.utils.lf(), (filename))



                
    def load(self): 
        """ Main load function for downloading DICOM files
            from an XNAT server and loading them into Slicer. 
            The general approach is as follows: 
            
            1) Clear existing download path
            2) Acquire downloadables depending on the XNAT level.  
               (Experiment is the minimum download level.)
            2a) Check if downloadbles are chached in the slicer.dicomDatabase.  
                Track all cached files.
            3) Get the non-cached downloadables by zipped folder files.
            4) Conduct the necessary caching and file management of the download.
            5) Insert downloaded DICOMS into slicer.dicomDatabase
            6) Query the database for the recently downloaded DICOMs
            7) Acquire "Loadables" based on database query.
            8) Load loadables with highest file count to Slicer.
        """

            
        experimentsList = []
        scansList = []   


            
        #--------------------
        # Remove existing files in the local download path (self.localDst)
        # if they exist.
        #--------------------
        if os.path.exists(self.localDst) and os.path.isdir(self.localDst):
            self.MODULE.utils.removeFilesInDir(self.localDst)
        if not os.path.exists(self.localDst): 
            os.makedirs(self.localDst)
        print(self.MODULE.utils.lf(), "Downloading DICOMS in '%s'."%(self.xnatSrc),"Please wait.") 

        

                        
        #--------------------
        # EXPERIMENT - get downloadables.
        #--------------------
        if self.XnatLevel == 'experiments':
            #print(self.MODULE.utils.lf(), "Retrieving experiment-level DICOMS.") 
            
            #
            # First, get the downloadables at the current URI.
            #
            self.getDownloadables(os.path.dirname(self.xnatSrc)) 
            
            #
            # Then, scan the folder contents of the 'scan' folders within
            # the experiment.  Get the downloadables accordingly.
            #
            scansList, sizes = self.MODULE.XnatIo.getFolderContents(self.xnatSrc, self.MODULE.utils.XnatMetadataTags_experiments)
            for scan in scansList:
                self.getDownloadables(self.xnatSrc + "/" + scan)


                    
        #--------------------
        # SCANS - get downloadables.
        #--------------------
        elif self.XnatLevel == 'scans':
            selector = self.xnatSrc.split("/files")[0] if self.xnatSrc.endswith('/files') else self.xnatSrc
            self.getDownloadables(selector)   


                
        #--------------------
        # RESOURCES - get downloadables.
        #--------------------
        elif self.XnatLevel == 'resources':
            self.getDownloadables(self.xnatSrc.split("/resources")[0])      
        


        #--------------------
        # Exit out if there are no downloadables.
        #--------------------           
        if len(self.downloadables) == 0:
            downloadFail = "No scans in '%s' found to download."%(self.xnatSrc)
            if self.MODULE.XnatLoadWorkflow.currentDownloadState == 'single':
                self.MODULE.XnatDownloadPopup.hide()
                self.MODULE.XnatIo.downloadFailed('Download failed', downloadFail)
            else:
                print downloadFail
            return 


        
        #--------------------
        # Set the local download path.
        #--------------------         
        if self.localDst.endswith("/"):
            self.localDst = self.localDst[:-2]                
        if not os.path.exists(self.localDst):
            os.mkdir(self.localDst)  



        
        #--------------------
        # Construct a dictionary that maps remote
        # src files to local dst files.
        #--------------------           
        downloadDictionary = dict(zip(self.downloadables, [(self.localDst + "/" + os.path.basename(dcm)) for dcm in self.downloadables]))

        print downloadDictionary
        #return

        #--------------------
        # CACHING: Check the slicer.dicomDatabase to see if 
        # the files already exist.
        #--------------------
        dicomFilenames = [(os.path.basename(dcm)) for dcm in self.downloadables]
        foundDicoms = {}
        for dbFile in slicer.dicomDatabase.allFiles():
            dbBasename = os.path.basename(dbFile)
            if dbBasename in dicomFilenames:
                foundDicoms[dbBasename] = dbFile
        if len(foundDicoms) > 0:
            print self.MODULE.utils.lf(), "Several of the DICOMs to download are already in the cache!"


            
        #--------------------
        # Establish the downloadedDicoms array.
        #--------------------
        downloadedDicoms = []


        
        #--------------------
        # Cull any of the cached DICOMSs from the downloadDictionary,
        # adding them to the 'downloadedDicoms' array.
        #--------------------
        newDownloadDictionary = {}
        for key, value in downloadDictionary.iteritems():
            keyBasename = os.path.basename(key) 
            if not keyBasename in foundDicoms:
                newDownloadDictionary[key] = value
            else:
                
                #
                # Add cached files to the 'downloadedDicoms'
                # array.
                #
                downloadedDicoms.append(foundDicoms[keyBasename])
        downloadDictionary =  newDownloadDictionary


        
        
        #--------------------
        # DOWNLOAD: Download all un-cached DICOMS as part of a zipped file.
        #--------------------  
        zipFolders = self.MODULE.XnatIo.getFiles(downloadDictionary)
        
        #
        # Close the download popup, in case it's visible.
        #
        self.MODULE.XnatDownloadPopup.window.hide()


        

        
        #--------------------
        # Reenable the XnatView so the user
        # can interact with it.
        #--------------------
        self.MODULE.XnatView.setEnabled(True)
        slicer.app.processEvents()

        
            
        #--------------------
        # Inventory downloaded zipfile
        #--------------------
        
        for zipFile in zipFolders:
        
            extractPath = zipFile.split(".")[0]
            
            #
            # Remove existing zipfile extract path if it exists
            #
            if os.path.exists(extractPath): 
                self.MODULE.utils.removeDirsAndFiles(extractPath)

            #    
            # If the zipfile does not exist, then exit.
            # (This is the result of the Cancel button in 
            # the download modal being clicked.) 
            #
            if not os.path.exists(zipFile):
                print "%s exiting workflow..."%(self.MODULE.utils.lf())  
                return False

            
            #
            # Show the 'Processing DICOMs' QMessageBox if it's not open
            #
            if not self.processingDicomsMessageBox.visible:
                ##print "\n\n\t\tHiding processing DICOMS"
                self.MODULE.utils.repositionToMainSlicerWindow(self.processingDicomsMessageBox)
                self.processingDicomsMessageBox.show()
                
                

            #
            # Decompress zips.
            #
            print zipFile, extractPath
            self.MODULE.utils.decompressFile(zipFile, extractPath)

            #
            # Add to files in the decompressed destination 
            # to downloadedDicoms list.
            #
            print "%s Inventorying downloaded files..."%(self.MODULE.utils.lf())  
            for root, dirs, files in os.walk(extractPath):
                for relFileName in files:          
                    downloadedDicoms.append(self.MODULE.utils.adjustPathSlashes(os.path.join(root, relFileName)))
               


        #--------------------
        # Add DICOM files to slicer.dicomDataase
        #--------------------
        i = ctk.ctkDICOMIndexer()
        try:
            i.addListOfFiles(slicer.dicomDatabase, downloadedDicoms)
        except Exception, e:
            
            #
            # If the database is uninitialized, then initialize it.
            #
            errorString = str(e)
            if 'uninitialized ctkDICOMItem' in errorString:
                print (self.MODULE.utils.lf(), "The slicer.dicomDabase is unitialized (%s).  Initializing it."%(errorString))
                slicer.dicomDatabase.initialize()
                i.addListOfFiles(slicer.dicomDatabase, downloadedDicoms)



        #--------------------
        # Load the 'downloaded' DICOMS from Slicer's database.
        #--------------------
        return self.loadDicomsFromDatabase(downloadedDicoms)


    
    def loadDicomsFromDatabase(self, dicomFiles):
        """  Loads a set of dicom database files from the slicer.dicomDatabase
             into Slicer without prompting the user to input anything.  
             The 'loadable' with the hightest priority has the highest 
             file count.
        """
    
        #--------------------
        # Create dictionary of downloaded DICOMS
        # for quick retrieval when comparing with files
        # in the slicer.dicomDatabase.  Speed preferred over
        # memory consumption here.
        #--------------------      
        dlDicomObj = {}
        for dlFile in dicomFiles:
            dlDicomObj[os.path.basename(dlFile)] = dlFile


            
        #--------------------
        # Parse through the slicer.dicomDatabase
        # to get all of the files, as determined by series.
        #--------------------
        matchedDatabaseFiles = []
        for patient in slicer.dicomDatabase.patients():
            for study in slicer.dicomDatabase.studiesForPatient(patient):
                for series in slicer.dicomDatabase.seriesForStudy(study):
                    seriesFiles = slicer.dicomDatabase.filesForSeries(series)
                    #
                    # Compare files in series with what was just downloaded.
                    # If there's a match, append to 'matchedDatabaseFiles'.
                    #
                    for sFile in seriesFiles:
                       if os.path.basename(sFile) in dlDicomObj: 
                           matchedDatabaseFiles.append(sFile)


                           
        #--------------------
        # Acquire loadabes as determined by
        # the 'DICOMScalarVolumePlugin' class, by feeding in 
        # 'matchedDatabaseFiles' as a nested array.
        #--------------------
        dicomScalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
        loadables = dicomScalarVolumePlugin.examine([matchedDatabaseFiles])


        
        #--------------------
        # Determine loadable with the highest file count. 
        # This is usually all DICOM files collated as one volume.
        #--------------------
        highestFileCount = 0
        highestFileCountIndex = 0
        for i in range(0, len(loadables)):
            if len(loadables[i].files) > highestFileCount:
                highestFileCount = len(loadables[i].files)
                highestFileCountIndex = i


                
        #--------------------
        # Load loadable with the highest file count.
        # This is assumed to be the volume file that contains
        # the majority of the downloaded DICOMS.
        #--------------------
        dicomScalarVolumePlugin.load(loadables[highestFileCountIndex])
                    

        
        #--------------------
        # Hide the 'processing Dicoms' notification window.
        #--------------------
        self.processingDicomsMessageBox.hide()


        
        #--------------------
        # Return true if login successful.
        #--------------------        
        return True



            
    def beginDICOMSession(self):
        """ DEECATED: Once a DICOM folder has been downloaded, 
            track the origins of the files for Save/upload
            routines.

            NOTE:
        """
        #print(self.MODULE.utils.lf(), "DICOMS successfully loaded.")
        sessionArgs = XnatSessionArgs(MODULE = self.MODULE, srcPath = self.xnatSrc)
        sessionArgs['sessionType'] = "dicom download"
        self.MODULE.XnatView.startNewSession(sessionArgs)


