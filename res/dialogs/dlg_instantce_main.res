DIALOG DLG_INSTANTCE_MAIN
{
    NAME DLG_TITLE;
    SCALE_H;
    FIT_H;

    GROUP
    {
        SCALE_H;
        FIT_H;
        COLUMNS 2;
        BORDERSIZE 6, 6, 6, 6;
        
        GROUP
        {
            SCALE_H;
            FIT_H;
            COLUMNS 1;
            ROWS 0;
            BORDERSIZE 6, 6, 6, 6;
            // BORDERSTYLE BORDER_WITH_TITLE_BOLD;

            STATICTEXT {
                ALIGN_LEFT;
                SIZE 0, 15;
                NAME INSTANTCE_IDS_ADD_OBJECTS;
            }

            SUBDIALOG DLG_INSTANTCE_OBJECT_LIST {
                SIZE 500, 300;
                SCALE_H;
                FIT_H;
                SCALE_V;
                FIT_V;
            }
        }

        GROUP
        {
            SCALE_H;
            FIT_H;
            ALIGN_TOP;
            COLUMNS 1;

            STATICTEXT {
                ALIGN_LEFT;
                SIZE 0, 15;
                NAME INSTANTCE_IDS_SETTINGS;
            }

            GROUP
            {
                FIT_H;
                SCALE_H;
                BORDERSIZE 6, 6, 6, 6;
                NAME INSTANTCE_IDS_PRECISION;
                BORDERSTYLE BORDER_GROUP_IN;

                EDITSLIDER INSTANTCE_ID_PRECISION {
                    ALIGN_LEFT;
                    SCALE_H;
                    FIT_H;
                }
            }

            GROUP
            {
                FIT_H;
                SCALE_H;
                BORDERSIZE 6, 6, 6, 6;
                NAME INSTANTCE_IDS_SAMPLES;
                BORDERSTYLE BORDER_GROUP_IN;

                EDITSLIDER INSTANTCE_ID_SAMPLES {
                    ALIGN_LEFT;
                    SCALE_H;
                    FIT_H;
                }
            }

            GROUP
            {
                FIT_H;
                SCALE_H;
                BORDERSIZE 6, 6, 6, 6;
                NAME INSTANTCE_IDS_SEED;
                BORDERSTYLE BORDER_GROUP_IN;                    

                EDITNUMBERARROWS INSTANTCE_ID_SEED {
                    ALIGN_LEFT;
                    SCALE_H;
                    FIT_H;
                }
            }

            GROUP
            {
                FIT_H;
                SCALE_H;
                NAME INSTANTCE_IDS_CONSIDER;
                COLUMNS 1;
                BORDERSTYLE BORDER_GROUP_IN;
                BORDERSIZE 6, 4, 6, 6;

                CHECKBOX INSTANTCE_ID_CONSIDER_MATERIALS {
                    SCALE_H;
                    FIT_H;
                    NAME INSTANTCE_IDS_CONSIDER_MATERIALS;
                }
                CHECKBOX INSTANTCE_ID_CONSIDER_NORMALS {
                    SCALE_H;
                    FIT_H;
                    NAME INSTANTCE_IDS_CONSIDER_NORMALS;
                }
                CHECKBOX INSTANTCE_ID_CONSIDER_UVS {
                    SCALE_H;
                    FIT_H;
                    NAME INSTANTCE_IDS_CONSIDER_UVS;
                }
            }

            GROUP
            {
                FIT_H;
                SCALE_H;
                BORDERSTYLE BORDER_GROUP_IN;
                BORDERSIZE 6, 6, 6, 6;

                CHECKBOX INSTANTCE_ID_BLIND_MODE {
                    SCALE_H;
                    FIT_H;
                    NAME INSTANTCE_IDS_BLIND_MODE;
                }
            }
        }

        SEPARATOR { SCALE_H; }
    }

    GROUP
    {
        SCALE_H;
        FIT_H;
        SCALE_V;
        FIT_V;
        COLUMNS 0;
        ROWS 1;

        BORDERSTYLE BORDER_THIN_IN;

        PROGRESSBAR INSTANTCE_ID_PROGRESSBAR
        {
            FIT_H;
            SCALE_H;
            FIT_V;
            SCALE_V;
            SIZE 100, 10;
        }

        SEPARATOR { SCALE_V; FIT_V; }

        STATICTEXT INSTANTCE_ID_PROGRESSBAR_TEXT
        {
            SIZE 50, 10;

            // BORDERSTYLE BORDER_WITH_TITLE_BOLD
        }
    }

    SEPARATOR { SCALE_H; }
    GROUP{
        SCALE_H;
        FIT_H;
        COLUMNS 2;

        BUTTON INSTANTCE_ID_EXTRACT_BTN {
            SCALE_H;
            FIT_H;
            SIZE 0, 30;
            NAME INSTANTCE_IDS_EXTRACT_BTN;
        }
        BUTTON INSTANTCE_ID_PROCESS_BTN {
            SCALE_H;
            FIT_H;
            SIZE 0, 30;
            NAME INSTANTCE_IDS_PROCESS_BTN;
        }
    }
}