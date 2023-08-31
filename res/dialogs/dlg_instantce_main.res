DIALOG DLG_INSTANTCE_MAIN
{
    NAME DLG_TITLE;

    GROUP ID_OVERALLGRP
    {
        SCALE_H;
        FIT_H;
        COLUMNS 1;
        ROWS 0;

        SEPARATOR { SCALE_H; }

        GROUP
        {
            SCALE_H;
            FIT_H;
            COLUMNS 2;
            ROWS 0;
            BORDERSIZE 6, 6, 6, 6;
         
            GROUP
            {
                SCALE_H;
                FIT_H;
                COLUMNS 1;
                ROWS 0;
                BORDERSIZE 6, 6, 6, 6;

                STATICTEXT {
                    ALIGN_LEFT;
                    SIZE 0, 15;
                    NAME IDS_ADD_OBJECTS;
                    BORDER_WITH_TITLE_BOLD;
                }

                IN_EXCLUDE ID_INEXCLUDE_LIST {
                    // SIZE 500, 300;
                    SCALE_H;
                    FIT_H;
                    SCALE_V;
                    FIT_V;
                    NUM_FLAGS 1;
                    INIT_STATE 1;
                    IMAGE_01_ON RESOURCEIMAGE_OK; //300000131
                    IMAGE_01_OFF RESOURCEIMAGE_CANCEL; //300000130
                    ACCEPT { Opolygon; }
                }
            }

            GROUP
            {
                SCALE_H;
                FIT_H;
                ALIGN_TOP;
                COLUMNS 1;
                ROWS 0;

                STATICTEXT {
                    ALIGN_LEFT;
                    SIZE 0, 15;
                    NAME IDS_SETTINGS;
                    BORDER_WITH_TITLE_BOLD;
                }

                GROUP
                {
                    FIT_H;
                    SCALE_H;
                    NAME IDS_PRECISION;
                    BORDERSTYLE BORDER_GROUP_IN;
                    BORDERSIZE 6, 6, 6, 6;

                    EDITSLIDER ID_PRECISION {
                        SCALE_H;
                        FIT_H;
                    }
                }

                GROUP
                {
                    FIT_H;
                    SCALE_H;
                    NAME IDS_SAMPLES;
                    BORDERSTYLE BORDER_GROUP_IN;
                    BORDERSIZE 6, 6, 6, 6;

                    EDITSLIDER ID_SAMPLES {
                        SCALE_H;
                        FIT_H;
                    }
                }

                GROUP
                {
                    FIT_H;
                    SCALE_H;
                    NAME IDS_SEED;
                    BORDERSTYLE BORDER_GROUP_IN;
                    BORDERSIZE 6, 6, 6, 6;

                    EDITSLIDER ID_SEED {
                        SCALE_H;
                        FIT_H;
                    }
                }

                GROUP
                {
                    FIT_H;
                    SCALE_H;
                    NAME IDS_CONSIDER;
                    BORDERSTYLE BORDER_GROUP_IN;
                    BORDERSIZE 6, 6, 6, 6;

                    CHECKBOX ID_CONSIDER_MATERIALS {
                        SCALE_H;
                        FIT_H;
                        NAME IDS_CONSIDER_MATERIALS;
                    }
                    CHECKBOX ID_CONSIDER_NORMALS {
                        SCALE_H;
                        FIT_H;
                        NAME IDS_CONSIDER_NORMALS;
                    }
                    CHECKBOX ID_CONSIDER_UVS {
                        SCALE_H;
                        FIT_H;
                        NAME IDS_CONSIDER_UVS;
                    }
                }

                GROUP
                {
                    FIT_H;
                    SCALE_H;
                    BORDERSTYLE BORDER_GROUP_IN;
                    BORDERSIZE 6, 6, 6, 6;

                    CHECKBOX ID_BLIND_MODE {
                        SCALE_H;
                        FIT_H;
                        NAME IDS_BLIND_MODE;
                    }
                }
            }

            SEPARATOR { SCALE_H; }
            
            GROUP
            {
                SCALE_H;
                FIT_H;
                SCALE_V;
                FIT_V;
                COLUMNS 0;
                ROWS 1;

                BORDERSTYLE BORDER_THIN_IN;

                PROGRESSBAR ID_PROGRESSBAR
                {
                    FIT_H;
                    SCALE_H;
                    FIT_V;
                    SCALE_V;
                    SIZE 100, 10;
                }

                SEPARATOR { SCALE_V; FIT_V; }

                STATICTEXT ID_PROGRESSBAR_TEXT
                {
                    SIZE 50, 10;

                    BORDERSTYLE BORDER_WITH_TITLE_BOLD
                }
            }

            SEPARATOR { SCALE_H; }
            BUTTON ID_PROCESS_BTN {
                SCALE_H;
                FIT_H;
                SIZE 0, 30;
                NAME IDS_PROCESS_BTN;
            }

        }
    }


}